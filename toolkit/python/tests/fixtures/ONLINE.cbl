       IDENTIFICATION DIVISION.
       PROGRAM-ID. ONLINE.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  MENU-OPTIONS.
           05 MENU-OPTIONS-DATA.
              10 FILLER           PIC 9(02) VALUE 1.
              10 FILLER           PIC X(10) VALUE 'Accounts'.
              10 FILLER           PIC X(08) VALUE 'SAMPACCT'.
              10 FILLER           PIC 9(02) VALUE 2.
              10 FILLER           PIC X(10) VALUE 'Reports'.
              10 FILLER           PIC X(08) VALUE 'SAMPRPT'.
           05 MENU-TABLE REDEFINES MENU-OPTIONS-DATA.
              10 MENU-OPT OCCURS 3 TIMES.
                 15 MENU-OPT-NUM  PIC 9(02).
                 15 MENU-OPT-NAME PIC X(10).
                 15 MENU-OPT-PGM  PIC X(08).
       01  WS-OPTION              PIC 9(02).
       01  PSB-NAME               PIC X(08) VALUE 'SAMPPSB'.
       01  JOB-LINES.
           05 FILLER PIC X(80) VALUE
              "//SAMPRPT JOB 'REPORT',CLASS=A".
           05 FILLER PIC X(80) VALUE
              "//STEP10 EXEC PROC=SAMPPROC".
       01  MQTM                   PIC X(684).
       01  MQ-OD.
           05 MQOD-OBJECTNAME     PIC X(48).
       01  REQUEST-QUEUE          PIC X(48).
       01  MQ-HCONN               PIC S9(9) BINARY.
       01  MQ-HOBJ                PIC S9(9) BINARY.
       01  MQ-BUFFER              PIC X(100).
       PROCEDURE DIVISION.
       0000-MAIN.
           EXEC CICS RETRIEVE INTO(MQTM) END-EXEC
           PERFORM 1000-OPEN
           EXEC DLI SCHD PSB((PSB-NAME)) END-EXEC
           EXEC CICS XCTL PROGRAM(MENU-OPT-PGM(WS-OPTION)) END-EXEC.
       1000-OPEN.
           MOVE REQUEST-QUEUE TO MQOD-OBJECTNAME
           CALL 'MQOPEN' USING MQ-HCONN MQ-OD WS-OPTION MQ-HOBJ
           CALL 'MQGET' USING MQ-HCONN MQ-HOBJ MQ-BUFFER.
