#!/bin/bash

PROCESSING_XML="/nv/hp19/tburrows3/data/practice_project/practice_script.xml"
PROCESSINGMODE=0
PROJECT_PATH="/nv/hp19/tburrows3/data/practice_project/Travis_PIV_Date=20181009_Time=110058_W2"
SOURCE_PATH="/nv/hp19/tburrows3/data/practice_project/Travis_PIV_Date=20181009_Time=110058_W2/RPM2400Q0_dt1.25/MaskCreateGeometric"
RESULT_PATH="/nv/hp19/tburrows3/data/practice_project/Travis_PIV_Date=20181009_Time=110058_W2/RPM2400Q0_dt1.25/MaskCreateGeometric/PIV_MP(4x16x16_50%ov_ImgCorr)"
FIRSTFILE=1
LASTFILE=100
STEPFILES=1
HASHVALUE=1315337431

if test "$OMPI_COMM_WORLD_RANK" == "" ; then
	OMPI_COMM_WORLD_RANK=0
	OMPI_COMM_WORLD_SIZE=1
fi

/nv/hp19/tburrows3/davis/davis-start.sh -stdoff  -csp "$PROCESSING_XML" $OMPI_COMM_WORLD_RANK $OMPI_COMM_WORLD_SIZE $PROCESSINGMODE "$PROJECT_PATH" "$SOURCE_PATH" "$RESULT_PATH" $FIRSTFILE $LASTFILE $STEPFILES $HASHVALUE

