#!/bin/bash
tnftp localhost 2121 <<FTP
quote site filetype=JES
put jcl/SAMPJOB.jcl
bye
FTP
