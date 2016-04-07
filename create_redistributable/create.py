#!/usr/bin/env python
import os, sys, argparse, shutil, platform, subprocess, tempfile

### PackageMaker location (default on OS X)
_package_maker = '/Applications/PackageMaker.app/Contents/MacOS/PackageMaker'

### List of OS X versions that need a symbolic link to openmp
_need_symbolic_link = ['10.11', '10.12']

### A dictionary of package types corresponding to OS type
_pathetic_dict = {RPM : ['FEDORA', 'SUSE', 'CENTOS', 'RHEL'],
                  DEB : ['UBUNTU', 'MINT', 'DEBIAN', 'KUBUNTU'],
                  PKG : ['DARWIN']}

### Conversion of OS X version to release name
_mac_version_to_name = {'10.9'  : 'mavericks',
                        '10.10' : 'yosemite',
                        '10.11' : 'elcapitan',
                        '10.12' : 'fuji'}

class PackageCreator:
  """
Base class for building packages
"""
  def __init__(self):
    if self.uname.upper().find('DARWIN') != -1:
      self.system = 'darwin'
      self.version = '.'.join(platform.mac_ver()[0].split('.')[:-1])
      self.release = _mac_version_to_name[self.version]
    else:
      self.system, self.version, self.release = platform.linux_distribution()

    self.temp_dir = tempfile.mkdtemp()
    self.uname = platform.platform()
    self.redistributable_version = self._get_build_version()
    self.redistributable_name = self.release + '-environment_' + str(self.redistributable_version) + '.' + self.__class__.__name__.lower()

  def _get_build_version(self):
    if not os.path.exists(os.path.join(args.relative_path, self.__class__.__name__.lower(), self.version + '_build')):
      with open(os.path.join(args.relative_path, self.__class__.__name__.lower(), self.version + '_build'), 'w') as version_file:
        version_file.write('1')
        return '1'
    else:
      with open(os.path.join(args.relative_path, self.__class__.__name__.lower(), self.version + '_build'), 'r+') as version_file:
        new_version = int(version_file.read()) + 1
        version_file.truncate(0)
        version_file.seek(0)
        version_file.write(str(new_version))
        return new_version

  def prepare_area(self):
    try:
      #shutil.copytree(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), self.__class__.__name__.lower()), self.temp_dir, symlinks=False, ignore=None)
      print 'copy tree:\n', os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), self.__class__.__name__.lower()) , self.temp_dir
    except os.error, err:
      return False, err
    return True

  def create_tarball(self, source):
    try:
      #shutil.make_archive(os.path.join(self.temp_dir, self.__class__.__name__.lower()), 'gztar', source)
      print 'Create tarball:', os.path.join(self.temp_dir, self.__class__.__name__.lower()), 'gztar', source
    except os.error, err:
      return False, err
    return True

  def create_redistributable(self):
    return True

  def commit_version_change(self):
    return True

class DEB(PackageCreator):
  """
Class for building Debian based packages
"""
  def create_redistributable(self):
    return True
  def commit_version_change(self):
    return True

class RPM(PackageCreator):
  """
Class for building RedHat based packages
"""
  def create_redistributable(self):
    return True
  def commit_version_change(self):
    return True


class PKG(PackageCreator):
  """
Class for building Macintosh Packages
"""
  def __init__(self, args):
    self.args = args
    self.arch = OSArch()
    self.redistributable_version = self._get_build_version()
    self.redistributable_name = self.arch.release + '-environment_' + str(self.redistributable_version) + '.pkg'

  def _get_build_version(self):
    # Increment our redistributable version
    with open(os.path.join(args.relative_path, 'pkg/OSX', self.arch.version + '_build'), 'a') as version_file:
      new_version = int(version_file.read()) + 1
      version_file.truncate(0)
      version_file.seek(0)
      version_file.write(str(new_version))
      return new_version

  def prepare_area(self):
    if prepare_area(self.args, self.arch):
      # Iterate through all files in the template pmdoc directory and modify version specs
      for directory, directories, files in os.walk(os.path.join(self.arch.temp_dir, '-'.join([self.arch.system, self.arch.version]), 'OSX.pmdoc')):
        for xml_file in files:
          with open(os.path.join(self.arch.temp_dir, '-'.join([self.arch.system, self.arch.version]), 'OSX.pmdoc', xml_file), 'a') as tmp_file:
            xml_string = tmp_file.read()
            tmp_file.truncate(0)
            tmp_file.seek(0)
            xml_string = xml_string.replace('<MAC_VERSION>', self.arch.version)
            xml_string = xml_string.replace('<REDISTRIBUTABLE_FILE>', self.arch.redistributable_name)
            tmp_file.write(xml_string)

      # Iterate through the all control files that redistributable package uses during installation and
      # make some path/version specific changes based on machine type
      for html_file in ['README_Panel.html', 'Welcome_Panel.html', 'cleanup_post.sh', 'payload_post.sh', 'common_post.sh', 'environment_post.sh']:
        with open(os.path.join(self.arch.temp_dir, '-'.join([self.arch.system, self.arch.version]), 'OSX', html_file), 'a') as tmp_file:
          html_str = tmp_file.read()
          tmp_file.truncate(0)
          tmp_file.seek(0)

          # If we are only building a package for OS X El Capitan (10.11), set a special
          # switch that allows the installer to create a symbolic link to our openMP
          # implementation (DYLD_LIBRARY_PATH issue)
          if html_file == 'common_post.sh' and self.arch.version in _need_symbolic_link:
            html_str = html_str.replace('<BOOL>', '1')
          else:
            html_str = html_str.replace('<BOOL>', '0')

          html_str = html_str.replace('<PACKAGES_DIR>', self.args.packages_dir)
          html_str = html_str.replace('<REDISTRIBUTABLE_VERSION>', 'Package version: ' + str(self.redistributable_version))
          tmp_file.write(html_str)
      return True
    return False

  def create_tarball(self):
    print 'Building tarball. This step can take a while...'
    os.chdir(self.args.packages_dir)
    try:
      shutil.make_archive(os.path.join(self.arch.temp_dir, '-'.join([self.arch.system, self.arch.version]), 'OSX', 'payload'), 'gztar', '.')
      print 'Tarball created'
    except os.error, err:
      print 'there was an error building tarball:', err
      return False
    return True

  def create_redistributable(self):
    os.chdir(os.path.join(self.arch.temp_dir, '-'.join([self.arch.system, self.arch.version])))
    print 'Building redistributable package. This step can also take some time...'
    package_builder = subprocess.Popen([self.args.package_maker, '--doc', os.path.join(self.arch.temp_dir, '-'.join([self.arch.system, self.arch.version]), 'OSX.pmdoc')],
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE,
                                       shell=False)

    results = package_builder.communicate()
    if len(results[1]) >= 1:
      print 'There was error building the redistributable package using PackageMaker:\n\n', results[1]
      return False
    else:
      return True

  def commit_version_change(self):
    ### TODO
    # Interface with git and commit/push the changes upstream
    return True

def verifyArgs(args):
  fail = False

  # Try to determine package type, unless provided by the user
  if args.package_type is None:
    for package_type, arch_list in _pathetic_dict.iteritems():
      for arch in arch_list:
        if arch in platform.platform().upper():
          args.package_type = package_type
  else:
    for package_type, arch_list in _pathetic_dict.iteritems():
      if package_type.__name__ == args.package_type.upper():
        args.package_type = package_type

  # Package type is still none?
  if args.package_type is None:
    print 'Unable to determine package type. You must provide package type manually.\n' \
      'See --help for supported package types'
    fail = True

  # Add _package_maker to argparser namespace for easy access
  args.package_maker = _package_maker

  # Add absolute path location of execution script to
  # argparser namespace for easy access
  args.relative_path = os.path.abspath(os.path.dirname(sys.argv[0]))

  # Check to see if Package Maker even exists. Its the
  # point to this script after all
  if args.package_type == 'PKG' and not os.path.exists(args.package_maker):
    print '* Error: Package Maker does not appear to be installed in its default\n' \
      'location of:\n', args.package_maker, '\n'
    fail = True

  # Is what we are trying to distribute available?
  if args.packages_dir:
    if not os.path.exists(args.packages_dir):
      print '* Error: path provided:', args.packages_dir, 'not found'
      fail = True
  else:
    print '* Error: you need to supply a --packages-dir argument pointing\n' \
      'to where you installed everything to (--packages-dir /opt/moose)\n'
    fail = True

  if fail:
    print '\nPlease solve for the failures identified and re-run this script'
    sys.exit(1)
  return args

def parseArguments(args=None):
  parser = argparse.ArgumentParser(description='Create Redistributable Package')
  parser.add_argument('-p', '--packages-dir', help='Directory where you installed everything to (/opt/moose)')
  parser.add_argument('--package-type', help='Specify type of package to build. Valid values: deb rpm pkg')
  return verifyArgs(parser.parse_args(args))


if __name__ == '__main__':
  args = parseArguments()
  package = args.package_type(args)
  if package.prepare_area():
    if package.create_tarball():
      if package.create_redistributable():
        print 'profit!'
