#!/usr/bin/python

import roslib; roslib.load_manifest("job_generation")
import optparse
import hudson
import urllib
import time
import re
import os
import rosdistro

BOOTSTRAP_SCRIPT = """
cat &gt; $WORKSPACE/script.sh &lt;&lt;DELIM
#!/usr/bin/env bash
set -o errexit
echo "_________________________________BEGIN SCRIPT______________________________________"
sudo apt-get install bzr --yes
sudo apt-get install ros-ROSDISTRO-ros --yes
source /opt/ros/ROSDISTRO/setup.sh

export INSTALL_DIR=/tmp/install_dir
export WORKSPACE=/tmp/ros
export ROS_TEST_RESULTS_DIR=/tmp/ros/test_results
export JOB_NAME=$JOB_NAME
export BUILD_NUMBER=$BUILD_NUMBER
export HUDSON_URL=$HUDSON_URL
export ROS_PACKAGE_PATH=\$INSTALL_DIR/ros_release:/opt/ros/ROSDISTRO/stacks

mkdir -p \$INSTALL_DIR
cd \$INSTALL_DIR

scp jenkins@cob-kitchen-server:~/.gitconfig ~/.gitconfig
wget  --no-check-certificate http://code.ros.org/svn/ros/installers/trunk/hudson/hudson_helper 
chmod +x  hudson_helper
svn co https://code.ros.org/svn/ros/stacks/ros_release/trunk ros_release
""" #TODO hudson_helper and ros_release from hudson stack on github
# scp user???

SHUTDOWN_SCRIPT = """
echo "_________________________________END SCRIPT_______________________________________"
DELIM

set -o errexit

rm -rf $WORKSPACE/test_results
rm -rf $WORKSPACE/test_output

wget https://github.com/ipa320/hudson/raw/master/run/devel_run_chroot.py -O $WORKSPACE/devel_run_chroot.py
chmod +x $WORKSPACE/devel_run_chroot.py
cd $WORKSPACE &amp;&amp; $WORKSPACE/devel_run_chroot.py --distro=UBUNTUDISTRO --arch=ARCH --debug-chroot --ramdisk --ramdisk-size 6000M --hdd-scratch=/home/rosbuild/install_dir --script=$WORKSPACE/script.sh --ssh-key-file=/home/rosbuild/rosbuild-ssh.tar --repo-url http://cob-kitchen-server:3142/de.archive.ubuntu.com/ubuntu
""" #TODO --ssh-key ??? & wget devel_run_chroot.py from other location

# the supported Ubuntu distro's for each ros distro
ARCHES = ['amd64', 'i386']

# ubuntu distro mapping to ros distro
UBUNTU_DISTRO_MAP = ['lucid', 'maverick', 'natty']

# Path to hudson server
SERVER = 'http://cob-kitchen-server:8080'

# list of public an d private IPA Fraunhofer stacks
FHG_STACKS_PUBLIC = ['cob_extern', 'cob_common', 'cob_driver', 'cob_simulation', 'cob_apps']
FHG_STACKS_PRIVATE = ['cob3_intern', 'interaid', 'srs']

EMAIL_TRIGGER="""
        <hudson.plugins.emailext.plugins.trigger.WHENTrigger> 
          <email> 
            <recipientList></recipientList> 
            <subject>$PROJECT_DEFAULT_SUBJECT</subject> 
            <body>$PROJECT_DEFAULT_CONTENT</body> 
            <sendToDevelopers>SEND_DEVEL</sendToDevelopers> 
            <sendToRecipientList>true</sendToRecipientList> 
            <contentTypeHTML>false</contentTypeHTML> 
            <script>true</script> 
          </email> 
        </hudson.plugins.emailext.plugins.trigger.WHENTrigger> 
"""


def get_depends_one(stack_name, githubuser):
    # in case the 'stack' is cob3_intern
    if stack_name == "cob3_intern":
        return [str(d) for d in get_cob3_intern_deps]
    # get stack.xml from github
    stack_xml = get_stack_xml(stack_name, githubuser, get_stack_membership(stack_name))
    # convert to list
    depends_one = [str(d) for d in stack_manifest.parse(stack_xml).depends]
    return depends_one


def get_depends_all(stack_name, depends_all, githubuser):
    #TODO output
    depend_all_list = []
    start_depth = len(depends_all)
    print start_depth, " depends all ", stack_name
    [[depend_all_list.append(value) for value in valuelist] for valuelist in depend_all.itervalues()]
    if not stack_name in depends_all_list:
        # append stack to the right list in depend_all
        depends_all[get_stack_membership(stack_name)].append(stack_name)
        # find and append all IPA dependencies
        if get_stack_membership(stack_name) == "private" or get_stack_membership(stack_name) == "public":
            for d in get_depends_one(stack_name, githubuser):
                get_depends_all(d, depends_all, githubuser)
    print start_depth, " DEPENDS_ALL ", stack_name, " end depth ", len(depends_all)


def get_stack_membership(stack_name):
    if stack_name in FHG_STACKS_PUBLIC:
        return "public"
    elif stack_name in FHG_STACKS_PRIVATE:
        return "private"
    else:
        return "other"


#TODO check whether stack is forked on github or not
def stack_forked(githubuser, stack_name):
    
    git_auth = get_auth_keys(github)
    post = {'login' : git_auth.group(1), 'token' : git_auth.group(2)}
    fields = urllib.urlencode(post)
    
    path = "https://github.com/" + githubuser + "/" + stack + "/blob/master/Makefile"
    file1 = StringIO.StringIO()
    
    c = pycurl.Curl()
    c.setopt(pycurl.URL, path)
    c.setopt(pycurl.POSTFIELDS, fields)
    c.setopt(pycurl.WRITEFUNCTION, file1.write) # to avoid to show the called page
    c.perform()
    c.close
    if c.getinfo(pycurl.HTTP_CODE) == 200:
        return True
    else:
        print "ERRORCODE: ", c.getinfo(pycurl.HTTP_CODE)
        return False
        
def get_stack_xml(stack_name, githubuser):
    if not stack_forked(githubuser, stack_name):
        githubuser = "ipa320"
    try:
        git_auth = get_auth_keys(github)
        post = {'login' : git_auth.group(1), 'token' : git_auth.group(2)}
        fields = urllib.urlencode(post)
        
        path = "https://raw.github.com/" + githubuser + "/" + stack_name + "/master/stack.xml"
        tmpfile = StringIO.StringIO()
        
        c = pycurl.Curl()
        c.setopt(pycurl.URL, path)
        c.setopt(pycurl.POSTFIELDS, fields)
        c.setopt(pycurl.WRITEFUNCTION, tmpfile.write)
        c.perform()
        stack_xml = tmpfile.getvalue()
        c.close
    except :
        #TODO
        pass
    return stack_xml


def get_cob3_intern_deps(githubuser):
    # use until cob3_intern is split ino stacks
    if not stack_forked(githubuser, "cob3_intern"):
        githubuser = "ipa320"
    try:
        git_auth = get_auth_keys(github)
        post = {'login' : git_auth.group(1), 'token' : git_auth.group(2)}
        fields = urllib.urlencode(post)
        
        path = "https://raw.github.com/" + githubuser + "/" + stack_name + "/master/stack.xml"
        tmpfile = StringIO.StringIO()

        c = pycurl.Curl()
        c.setopt(pycurl.URL, path)
        c.setopt(pycurl.POSTFIELDS, fields)
        c.setopt(pycurl.WRITEFUNCTION, tmpfile.write)
        c.perform()
        stack_xml = tmpfile.getvalue()
        c.close
    except :
        #TODO
        pass
    
    
        
def get_auth_keys(server):
    # get password/token from .gitconfig file
    gitconfig = open("~/.gitconfig", "r") 
    gitconfig = gitconfig.read()
    # extract necessary data
    if server == "github":
        regex = ".*\[" + server + "]\s*user\s*=\s*([^\s]*)\s*token\s*=\s*([^\s]*).*"
    elif server == "jenkins":
        regex = ".*\[" + server + "]\s*user\s*=\s*([^\s]*)\s*password\s*=\s*([^\s]*).*"
    else:
        print "ERROR: invalid server"
        # TODO error raise
    auth_keys = re.match(regex, gitconfig, re.DOTALL)
    return auth_keys


def get_environment():
    my_env = os.environ
    my_env['WORKSPACE'] = os.getenv('WORKSPACE', '')
    my_env['INSTALL_DIR'] = os.getenv('INSTALL_DIR', '')
    #my_env['HOME'] = os.getenv('HOME', '')
    my_env['HOME'] = os.path.expanduser('~')
    my_env['JOB_NAME'] = os.getenv('JOB_NAME', '')
    my_env['BUILD_NUMBER'] = os.getenv('BUILD_NUMBER', '')
    my_env['ROS_TEST_RESULTS_DIR'] = os.getenv('ROS_TEST_RESULTS_DIR', my_env['WORKSPACE']+'/test_results')
    my_env['PWD'] = os.getenv('WORKSPACE', '')
    return my_env


def get_options(required, optional):
    parser = optparse.OptionParser()
    ops = required + optional
    if 'os' in ops:
        parser.add_option('--os', dest = 'os', default='ubuntu', action='store',
                          help='OS name')
    if 'rosdistro' in ops:
        parser.add_option('--rosdistro', dest = 'rosdistro', default=None, action='store',
                          help='Ros distro name')
    if 'stack' in ops:
        parser.add_option('--stack', dest = 'stack', default=None, action='append',
                          help='Stack name')
    if 'githubuser' in ops:
        parser.add_option('--githubuser', dest = 'githubuser', default=None, action="store",
                          help='Login name of github account')
    if 'email' in ops:
        parser.add_option('--email', dest = 'email', default=None, action='store',
                          help='Email address to send results to')
    if 'arch' in ops:
        parser.add_option('--arch', dest = 'arch', default=None, action='append',
                          help='Architecture to test')
    if 'ubuntu' in ops:
        parser.add_option('--ubuntu', dest = 'ubuntu', default=None, action='append',
                          help='Ubuntu distribution to test')
    if 'repeat' in ops:
        parser.add_option('--repeat', dest = 'repeat', default=0, action='store',
                          help='How many times to repeat the test')
    if 'source-only' in ops:
        parser.add_option('--source-only', dest = 'source_only', default=False, action='store_true',
                          help="Build everything from source, don't use Debian packages")
    if 'delete' in ops:
        parser.add_option('--delete', dest = 'delete', default=False, action='store_true',
                          help='Delete jobs from Hudson')    
    if 'wait' in ops:
        parser.add_option('--wait', dest = 'wait', default=False, action='store_true',
                          help='Wait for running jobs to finish to reconfigure them')    
    if 'rosinstall' in ops:
        parser.add_option('--rosinstall', dest = 'rosinstall', default=None, action='store',
                          help="Specify the rosinstall file that refers to unreleased code.")
    if 'overlay' in ops:
        parser.add_option('--overlay', dest = 'overlay', default=None, action='store',
                          help='Create overlay file')
    if 'variant' in ops:
        parser.add_option('--variant', dest = 'variant', default=None, action='store',
                          help="Specify the variant to create a rosinstall for")
    if 'database' in ops:
        parser.add_option('--database', dest = 'database', default=None, action='store',
                          help="Specify database file")

    (options, args) = parser.parse_args()
    

    # make repeat an int
    if 'repeat' in ops:
        options.repeat = int(options.repeat)

    # check if required arguments are there
    for r in required:
        if not eval('options.%s'%r):
            print 'You need to specify "--%s"'%r
            return (None, args)

    # postprocessing
    if 'email' in ops and options.email and not '@' in options.email:
        print 'You provided an invalid email address'
        return (None, args)       


    # check if rosdistro exists
#    if 'rosdistro' in ops and (not options.rosdistro or not options.rosdistro in UBUNTU_DISTRO_MAP.keys()):
#        print 'You provided an invalid "--rosdistro %s" argument. Options are %s'%(options.rosdistro, UBUNTU_DISTRO_MAP.keys())
#        return (None, args)

    # check if stacks exist
    #if 'stack' in ops and options.stack:
        #distro_obj = rosdistro.Distro(get_rosdistro_file(options.rosdistro))
        #for s in options.stack:
            #if not s in distro_obj.stacks:
                #print 'Stack "%s" does not exist in the %s disro file.'%(s, options.rosdistro)
                #print 'You need to add this stack to the rosdistro file'
                #return (None, args)

    # check if variant exists
    if 'variant' in ops and options.variant:
        distro_obj = rosdistro.Distro(get_rosdistro_file(options.rosdistro))
        if not options.variant in distro_obj.variants:
                print 'Variant "%s" does not exist in the %s disro file.'%(options.variant, options.rosdistro)
                return (None, args)

    return (options, args)


def schedule_jobs(jobs, wait=False, delete=False, start=False, hudson_obj=None):
    # create hudson instance
    if not hudson_obj:
        info = get_auth_keys('jenkins')
        hudson_obj = hudson.Hudson(SERVER, info.group(1), info.group(2))

    finished = False
    while not finished:
        jobs_todo = {}
        for job_name in jobs:
            exists = hudson_obj.job_exists(job_name)

            # job is already running
            if exists and hudson_obj.job_is_running(job_name):
                jobs_todo[job_name] = jobs[job_name]
                print "Not reconfiguring running job %s because it is still running"%job_name


            # delete old job
            elif delete:
                if exists:
                    hudson_obj.delete_job(job_name)
                    print " - Deleting job %s"%job_name

            # reconfigure job
            elif exists:
                hudson_obj.reconfig_job(job_name, jobs[job_name])
                if start:
                    hudson_obj.build_job(job_name)
                print " - %s"%job_name

            # create job
            elif not exists:
                hudson_obj.create_job(job_name, jobs[job_name])
                if start:
                    hudson_obj.build_job(job_name)
                print " - %s"%job_name

        if wait and len(jobs_todo) > 0:
            jobs = jobs_todo
            jobs_todo = {}
            time.sleep(10.0)
        else:
            finished = True


def get_rosdistro_file(rosdistro):
    return 'https://code.ros.org/svn/release/trunk/distros/%s.rosdistro'%rosdistro


def get_email_triggers(when, send_devel=True):
    triggers = ''
    for w in when:
        trigger = EMAIL_TRIGGER
        trigger = trigger.replace('WHEN', w)
        if send_devel:
            trigger = trigger.replace('SEND_DEVEL', 'true')
        else:
            trigger = trigger.replace('SEND_DEVEL', 'false')
        triggers += trigger
    return triggers


def get_job_name(rosdistro, stack_name, githubuser, ubuntu="", arch="", jobtype=""):
    if len(stack_name) > 50:
        stack_name = stack_name[0:46]+'_...'
    stack_name = "_".join(stack_name)
    if jobtype == "pipe":
        return "__".join([rosdistro, githubuser, stack_name, "pipe"])
    else:
        return "__".join([rosdistro, githubuser, stack_name, ubuntu, arch])    
