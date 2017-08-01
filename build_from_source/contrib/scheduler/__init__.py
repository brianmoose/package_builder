import subprocess
from time import sleep
from timeit import default_timer as clock
from multiprocessing.pool import ThreadPool
import threading # for thread locking and thread timers
import multiprocessing # for timeouts
from contrib import dag # contrib DAG
from signal import SIGTERM

class SchedulerError(Exception):
    pass

class Scheduler(object):
    """
    Class for launching jobs asyncronously using the contrib DAG object

    Syntax:
       my_scheduler = Scheduler(max_processes=#)
       my_scheduler.schedule(dag_object)
       my_scheduler.waitFinish()

    The object stored in the DAG should contain a run(), getResult() and killJob() method.

    run() method contains the work you want performed.
    getResult() can return anything, or what ever it is you want to print when the job is done.
    killJob() should kill what ever it is 'job' is doing.

    As jobs are finished they will be assigned to a new single process pool to perform getResult().

    """
    def __init__(self, max_processes=1, max_slots=1, load_average=64, term_width=70):

        # Max processes allowed per slot
        self.processes_per_slot = int(max_processes)

        # Maximum simultaneous slots (jobs)
        self.max_slots = int(max_slots)

        # Requested average load level to stay below
        self.load_average = load_average

        # Initialize tester pool
        self.worker_pool = ThreadPool(processes=self.processes_per_slot * self.max_slots)

        # Initialize status pool to only use 1 process (to prevent status messages from getting clobbered)
        self.status_pool = ThreadPool(processes=1)

        # Thread Locking
        self.thread_lock = threading.Lock()

        # Workers in use
        self.workers_in_use = 0

        # A simple queue increment to keep track of jobs
        self.job_queue_count = 0

        # A shared dictionary of dag objects
        self.shared_dags = {}

        # A set of already queued jobs
        self.active = set([])

        # Terminal width
        self.term_width = term_width

        # Maximum expected size of caveats
        self.max_caveat_length = 25

    def killJobs(self):
        """ loop through all active jobs and call their killJob method """
        self.status_pool.close()
        self.worker_pool.close()
        for job in self.active:
            try:
                job.killJob()
            except AttributeError:
                raise SchedulerError('killJob method is not defined')
            except: # Job already terminated
                pass
        print 'killing all jobs'
        self.job_queue_count = 0

    def waitFinish(self):
        """ block until all submitted jobs in all DAGs are finished """
        while self.job_queue_count > 0:
            sleep(0.5)

        self.worker_pool.close()
        self.worker_pool.join()
        self.status_pool.close()
        self.status_pool.join()

    def statusJob(self, job):
        """ call the job's getResults method """
        with self.thread_lock:
            name = job.name
            if job.status_done:
                job.addCaveat('time: ' + job.getTime())
                if job.getResult() == False:
                    self.killJobs()

                else:
                    self.job_queue_count -= 1
                    self.shared_dags[job].delete_node(job)
                    self.active.remove(job)
                    result = '-Finished  | '

            else:
                result = 'Launching  | '

            # Format job name length field
            name_cnt = self.term_width - len(job.name)
            result = result + job.name + ' '*name_cnt
            # Format caveat length
            caveats = job.getCaveats()
            caveat_cnt = self.max_caveat_length - len(caveats)

            if caveats:
                result = result + caveats + ' '*caveat_cnt
            else:
                result = result + ' '*caveat_cnt

            print result, 'active:', [x.name for x in self.active]

    def launchJob(self, job):
        """ call the job's run method """
        try:
            # Print initial status
            self.queueStatus(job)

            # Run the job
            job.run()

            # Print final status
            self.queueStatus(job)

        except AttributeError:
            raise SchedulerError('run method is not defined')

    def schedule(self, dag_object):
        """
        Account for all the jobs in the DAG and submit the DAG for
        processing.
        """
        if type(dag_object) != type(dag.DAG()):
            raise SchedulerError('schedule method requires a DAG object')

        if self.worker_pool._state:
            raise SchedulerError('scheduler is no longer accepting jobs')

        with self.thread_lock:
            self.job_queue_count += dag_object.size()
            for job in dag_object.topological_sort():
                # create pointer to DAG for every job
                self.shared_dags[job] = dag_object

        self.queueDAG(dag_object)

    def reserveAllocation(self, job, concurrent_jobs):
        """
        Return bool if there are enough resources to run job. Try to
        optimize allocated processors to this job, if we can.
        """
        with self.thread_lock:
            if job not in self.active and (job.serial or len(self.active) < self.max_slots):
                if job.serial:
                    job.addCaveat('serial')

                self.active.add(job)
                return True

    def queueDAG(self, job_dag):
        """
        Continue to assign workers for jobs that have yet to launch until
        there are no more jobs.
        """
        try:
            while job_dag.size():
                with self.thread_lock:
                    concurrent_jobs = job_dag.ind_nodes()
                for job in concurrent_jobs:
                    if self.reserveAllocation(job, concurrent_jobs) and self.worker_pool._state == 0:
                        self.worker_pool.apply_async(self.launchJob, (job,))
                sleep(.1)

        except KeyboardInterrupt:
            self.killJobs()
            pass

    def queueStatus(self, job):
        """ Assign a worker to a status job (print results to the screen) """
        self.status_pool.apply_async(self.statusJob, (job,))
