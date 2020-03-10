"""
batch-submit.py
This is a batch submit function for running Davis 8.4 on PACE.
@author: Travis Burrows
02/21/2020
"""

from subprocess import run, PIPE
from os.path import dirname, join, isfile, abspath, basename, splitext, isdir
from argparse import ArgumentParser, ArgumentTypeError, ArgumentDefaultsHelpFormatter
from math import floor
from sys import stderr, exit

def hoursToString(hours):
	wholeDays = floor(hours / 24.0)
	hours -= wholeDays * 24
	wholeHours = floor(hours)
	fractionHours = hours - wholeHours
	wholeMinutes = floor(fractionHours * 60)
	fractionMinutes = fractionHours*60 - wholeMinutes
	roundedSeconds = round(fractionMinutes * 60)
	walltime = '%02d:%02d:%02d' % (wholeHours, wholeMinutes, roundedSeconds)
	if wholeDays > 0:
		walltime = ('%02d:' % wholeDays) + walltime
	return walltime

def positive_float(x):
	try:
		x = float(x)
	except ValueError:
		raise ArgumentTypeError("%r not a floating-point literal" % x)
	if x < 0.0:
		raise ArgumentTypeError("%r has a negative value" % x)
	return x

def runcmd(command):
	output = run(command, stdout=PIPE, stderr=PIPE)
	output.stdout = output.stdout.decode('ascii')
	output.stderr = output.stderr.decode('ascii')
	if output.returncode == 1 or bool(output.stderr):
		raise ValueError('Error running "%s".\nSTDOUT:%s\nSTDERR:\n%s' % (command, output.stdout, output.stderr))
	return output.stdout

class MyParser(ArgumentParser):
	def error(self, message):
		stderr.write('error: %s\n' % message)
		print()
		self.print_help()
		exit(2)

# Parse arguments
parser = MyParser(description='Submit davis cluster script to PACE via qsub',  formatter_class=ArgumentDefaultsHelpFormatter)
parser.add_argument('script', type=str, help='Path of cluster script to submit')
parser.add_argument('procs', type=int, help='Number of processors to use')
parser.add_argument('hours',  type=positive_float, help='Time in hours to allow for job to complete (can be a decimal)')
parser.add_argument('-q','--queue', type=str, dest='queue', choices=['iw-shared-6', 'prometforce-6', 'prometheus'], default='iw-shared-6', help='Queue to which the job is submitted')
parser.add_argument('-m','--memory', type=int, dest='memory', default=4, help='Gigabytes of memory to allocate per processor')
parser.add_argument('-e','--email', dest='email', help='Email address to send notifications')
parser.add_argument('--debug', action='store_true', help='Store debug log files')
parser.add_argument('--do-not-submit', dest='donotsubmit', action='store_true', help='Generate PBS file but do not submit to PACE')

args = parser.parse_args()
scriptPath = abspath(args.script)
queue = args.queue
nProcs = args.procs
walltime = hoursToString(args.hours)
pmem = args.memory
email = args.email
debug = bool(args.debug)

if not isfile(scriptPath):
	raise ValueError('The script path is incorrect.  There is not a file at %s' % scriptPath)

scriptName = basename(scriptPath)
scriptWithoutExtension = splitext(scriptName)[0]
outputFile = scriptWithoutExtension + '.txt'

# Generate path for PBS file
scriptFolder = dirname(scriptPath)
pbsName = scriptWithoutExtension + '.pbs'
pbsFilename = join(scriptFolder, pbsName)

with open(scriptPath) as f:
		content = f.readlines()
		
numLines = len(content)

# Test to confirm files/folders exist that are referenced in script file
keywords = {'PROCESSING_XML':1, 'PROJECT_PATH':0, 'SOURCE_PATH':0, 'RESULT_PATH':0}
for label, IsFile in keywords.items():
	labelIndex = [ indx for indx, strng in zip(list(range(0, numLines)), content) if strng.startswith(label)]
	if (not len(labelIndex) == 1):
		raise ValueError('Error finding %s keyword' % (label))
	else:
		labelIndex = labelIndex[0]
	labelFilepath = content[labelIndex][(len(label)+2):-2]
	if (IsFile and (not isfile(labelFilepath))) or ((not IsFile) and (not isdir(labelFilepath))):
		if labelFilepath == '+':
			raise ValueError('Hyperlooping is not supported!')
		else:
			raise ValueError('%s has invalid path:%s' % (label, labelFilepath))

# Test to confirm davis-start.sh exists
davisKeyword = 'davis-start'
davisIndex = [ indx for indx, strng in zip(list(range(0, numLines)), content) if davisKeyword in strng]
if (not len(davisIndex) == 1):
	raise ValueError('Error finding %s keyword' % (davisKeyword))
else:
	davisIndex = davisIndex[0]
keywordIndex = content[davisIndex].index(davisKeyword)
davisPath = content[davisIndex][:keywordIndex-1]
davisStartPath = join(davisPath, 'davis-start.sh')
if not isfile(davisStartPath):
	raise ValueError('Davis path is invalid: %s' % (davisStartPath))

# If debug, remove -stdoff command from cluster script:
if debug:
	content[davisIndex] = content[davisIndex].replace('-stdoff','')
	with open(scriptPath,'w') as f:
		for line in content:
			f.write(line)

outputFilePath = join(scriptFolder, outputFile)

# Generate contents of temporary PBS script
pbsFile = []
pbsFile.append('#PBS -N %s' % scriptName)
pbsFile.append('#PBS -l nodes=%d:ppn=1' % nProcs)
pbsFile.append('#PBS -l pmem=%dgb' % pmem)
pbsFile.append('#PBS -l walltime=%s' % walltime)
pbsFile.append('#PBS -q %s' % queue)
pbsFile.append('#PBS -j oe')

if debug:
	pbsFile.append('#PBS -o %s' % outputFile)
else:
	pbsFile.append('#PBS -o /dev/null')
	
if bool(email):
	pbsFile.append('#PBS -m abe')
	pbsFile.append('#PBS -M %s' % email)

# Load mpi modules
pbsFile.append('module load java/1.8.0_25')
pbsFile.append('module load openmpi/2.1.1')

pbsFile.append('chmod +x %s' % scriptPath)

if debug:
	pbsFile.append('mpirun -v -np %d -machinefile $PBS_NODEFILE -output-filename %s %s' % (nProcs, outputFilePath, scriptPath))
else:
	pbsFile.append('mpirun -v -np %d -machinefile $PBS_NODEFILE %s' % (nProcs, scriptPath))

# Write PBS script
with open(pbsFilename,'w') as f:
	for line in pbsFile:
		f.write(line + '\n')

# Submit script to PACE
if not args.donotsubmit:
	output = runcmd(["qsub", pbsFilename])
	jobNumber = output[:output.index('.')]
	print('%s submitted to %s with %d processors' % (scriptName, queue, nProcs))
	print('Job number: %s' % jobNumber)
else:
	print('Successfully created %s and did not submit.' % pbsName)
