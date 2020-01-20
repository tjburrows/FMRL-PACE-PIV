"""
batch-submit-mpi.py
This is a batch submit script for parallelizing PIV processing on PACE with Davis 8.4.
@author: Travis Burrows
01/20/2020
"""

# Path to Davis script file, relative or absolute
scriptPath = 'practice_project.sh'

# Number of processors to split job across
nProcs = 20

# Time to allow for jobs to complete
walltime = '2:00:00'

# PACE Queue to submit to
queue = 'prometforce-6'

# Name of job to submit
name = 'BatchPIV'

# Memory for one node, in gigabytes.  4 should be fine for planar and stereo.
pmem = 4

# Toggle whether to debug
debug = 0

# Debug output files
outputFile = 'davisJobOutput.txt'


#############################
# Do not edit below this line
#############################

# Import functions
from re import fullmatch
from subprocess import run, PIPE
from os.path import dirname, join, isfile, abspath

# Checking parameters
if (not (debug == 1 or debug == 0)) or (not type(debug) == int):
	raise ValueError('debug parameter must be 1 or 0')

if not type(scriptPath) == str:
	raise ValueError('scriptPath parameter must be a string')

if not isfile(scriptPath):
	raise ValueError('The script path is incorrect.  There is not a file at %s' % scriptPath)
else:
	scriptPath = abspath(scriptPath)

if not type(nProcs) == int:
	raise ValueError('nProcs parameter must be an integer')

if not type(pmem) == int:
	raise ValueError('pmem parameter must be an integer')
	
if not type(walltime) == str:
	raise ValueError('walltime parameter must be a string')

if not type(queue) == str:
	raise ValueError('queue parameter must be a string')

if not type(outputFile) == str:
	raise ValueError('outputFile parameter must be a string')

# Runs command
def runcmd(command):
	output = run(command, stdout=PIPE, stderr=PIPE)
	output.stdout = output.stdout.decode('ascii')
	output.stderr = output.stderr.decode('ascii')
	if output.returncode == 1 or bool(output.stderr):
		raise ValueError('Error running "%s".\nSTDOUT:%s\nSTDERR:\n%s' % (command, output.stdout, output.stderr))
	return output.stdout

# Evenly allocates images to each processor
def SplitEvenly(total, numSplits):
	segments = []
	for i in range(0,numSplits):
		if i < (total % numSplits):
			segLength = total // numSplits + 1
			start = i*segLength
		else:
			segLength = total // numSplits
			start = total - (numSplits - i) * segLength
		segments.append([1 + start, start + segLength])
	return segments

# Generate path for PBS file
scriptFolder = dirname(scriptPath)
pbsFilename = scriptPath + ".pbs"
outputFile = join(scriptFolder, outputFile)  
  
# Read contents of original davis cluster script
with open(scriptPath) as f:
	content = f.readlines()

# Number of lines in file
numLines = len(content)

# Keywords to find image range
firstKeyword = 'FIRSTFILE='
lastKeyword = 'LASTFILE='

# Find line numbers of keywords
startIndex  = [ indx for indx, strng in zip(list(range(0, numLines)), content) if strng.startswith(firstKeyword)]
endIndex = [ indx for indx, strng in zip(list(range(0, numLines)), content) if strng.startswith(lastKeyword)]

# Check to make sure there is only one match of each
if (not len(startIndex) == 1) or (not len(endIndex) == 1):
	raise ValueError('Error finding %s or %s keywords' % (firstKeyword, lastKeyword))
else:
	startIndex = startIndex[0]
	endIndex = endIndex[0]

# Find davis executable
davisKeyword = 'davis-start'
davisIndex = [ indx for indx, strng in zip(list(range(0, numLines)), content) if davisKeyword in strng]
if (not len(davisIndex) == 1):
	raise ValueError('Error finding %s keyword' % (davisKeyword))
else:
	davisIndex = davisIndex[0]

# Create new davis path
keywordIndex = content[davisIndex].index(davisKeyword)
davisPath = content[davisIndex][:keywordIndex-1]
davisCommand = content[davisIndex][keywordIndex:]
davisCommand = davisCommand.replace('$OMPI_COMM_WORLD_RANK', '0')
davisCommand = davisCommand.replace('$OMPI_COMM_WORLD_SIZE', '1')
if debug:
    davisCommand = davisCommand.replace('-stdoff','')
newDavisPathBase = '${TMPDIR}/tempDavis'

# Find original start and stop numbers
startNumber = int(fullmatch(firstKeyword + '(\d+)\n', content[startIndex]).group(1))
endNumber = int(fullmatch(lastKeyword + '(\d+)\n', content[endIndex]).group(1))

# Compute number of images
numImages = endNumber - startNumber + 1

segmentRange = SplitEvenly(numImages, nProcs)

# Write a temporary davis cluster script for each segment
for i,segment in enumerate(segmentRange):
	newFilename = scriptPath + '.%d' % (i + 1)
	newFileContents = content.copy()
	newFileContents[startIndex] = firstKeyword + '%d\n' % segment[0]
	newFileContents[endIndex] = lastKeyword + '%d\n' % segment[1]
	newFileContents[davisIndex] = newDavisPathBase + '.%d/' % (i + 1) + davisCommand
	
	with open(newFilename,'w') as f:
		for line in newFileContents:
			f.write(line)
	
	# Make script executable
	output = run(['chmod', '+x', newFilename], stdout=PIPE, stderr=PIPE)
	if output.returncode:
		raise ValueError('chmod ')
	runcmd(['chmod', '+x', newFilename])


# Generate contents of C++ mpi file
cppFilename = join(scriptFolder, scriptPath + '.cpp')
cppFile = []
cppFile.extend(['#include <iostream>','#include <mpi.h>','\nusing namespace std;']);
cppFile.extend(['\nint runcmd(const string &command);', '\nint main(int argc, char *argv[]) {'])
cppFile.extend(['\n\tint rank{};','\n\t// Initialize MPI','\tconst int error = MPI_Init (&argc, &argv);'])
cppFile.extend(['\tif (error != 0) {cout << "\\nMPI Initialization error!\\n" << endl;return 1;}'])
cppFile.extend(['\n\t// Get rank','\tMPI_Comm_rank(MPI_COMM_WORLD, &rank);'])
cppFile.extend(['\n\t// Assign Job ID', '\tconst long long int jobID = rank + 1;'])
cppFile.extend(['\tconst string davisTempDir = "%s." + to_string(jobID);' % newDavisPathBase])
cppFile.extend(['\n\t// make directory','\tconst string mkdir = "mkdir -p " + davisTempDir;','\tif (runcmd(mkdir) == 1) return 1;'])
cppFile.extend(['\n\t// copy files','\tconst string oldDir = "%s";' % davisPath,'\tconst string copyCommand = "cp -ar " + oldDir + "/. " + davisTempDir;','\tif (runcmd(copyCommand) == 1) return 1;'])
cppFile.extend(['\n\t// setup cluster','\tconst string setupCommand = "cd \\"" + davisTempDir + "\\" && ./davis-setup.sh cluster\";','\tif (runcmd(setupCommand) == 1) return 1;'])
cppFile.extend(['\n\t// run command', '\tconst string originalScript = "%s";' % scriptPath, '\tconst string scriptPath = originalScript + "." + to_string(jobID);', '\tif (runcmd(scriptPath) == 1) return 1;'])
cppFile.extend(['\n\t// rm command','\tconst string rmCommand = "rm \\"" + scriptPath + "\\"";', '\tif (runcmd(rmCommand) == 1) return 1;'])
cppFile.extend(['\n\t// Finalize MPI','\tMPI_Finalize();'])
cppFile.extend(['\n\treturn 0;','}'])
cppFile.extend(['\nint runcmd(const string &command){'])
if debug:
    cppFile.extend(['\tprintf(command.c_str());','\tprintf("\\n");'])
cppFile.extend([ '\tconst int error = system(command.c_str());','\tif (error != 0) cout << "Error running command:\\n" + command << endl;','\treturn error;','}'])

# Write temporary c++ file
with open(cppFilename,'w') as f:
	for line in cppFile:
		f.write(line + '\n')

# Generate contents of temporary PBS script
pbsFile = []
pbsFile.append('#PBS -N %s' % name)
pbsFile.append('#PBS -l nodes=%d:ppn=1' % nProcs)
pbsFile.append('#PBS -l pmem=%dgb' % pmem)
pbsFile.append('#PBS -l walltime=%s' % walltime)
pbsFile.append('#PBS -l file=1gb')
pbsFile.append('#PBS -q %s' % queue)
pbsFile.append('#PBS -j oe')

if debug == 1:
	pbsFile.append('#PBS -o %s' % join(scriptFolder, outputFile))
else:
	pbsFile.append('#PBS -o /dev/null')

binaryFilename = scriptPath + '.bin'
pbsFile.append('module load java/1.8.0_25 openmpi/2.1.1')
pbsFile.append('mpic++ %s -std=c++0x -o %s' % (cppFilename, binaryFilename))

if debug:
	pbsFile.extend(['echo "Started on `/bin/hostname`"', 'echo', 'echo "Nodes chosen are:"', 'cat $PBS_NODEFILE', 'echo'])

	# Run davis
	pbsFile.append('mpirun -v -n %d -machinefile $PBS_NODEFILE -mca btl_sm_use_knem 0 --output-filename "%s" --timestamp-output "%s" &&' % (nProcs, outputFile, binaryFilename))

else:
    pbsFile.append('mpirun -n %d -machinefile $PBS_NODEFILE -mca btl_sm_use_knem 0 %s &&' % (nProcs, binaryFilename))

# Remove temporary files
pbsFile.append('rm "%s" "%s"' % (cppFilename, binaryFilename))

# Write temporary PBS script
with open(pbsFilename,'w') as f:
	for line in pbsFile:
		f.write(line + '\n')

# Submit script to PACE
output = runcmd(["qsub", pbsFilename])
jobNumber = output[:output.index('.')]
print('Job was successfully submitted to %s with %d processors' % (queue, nProcs))
print('Job number: %s' % jobNumber)
