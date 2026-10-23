       IDENTIFICATION DIVISION.
       PROGRAM-ID. MQCALL.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  MQ-OD.
           05 MQOD-OBJECTNAME     PIC X(48).
       01  MQM-OD-REPLY.
           05 MQOD-OBJECTNAME     PIC X(48).
       01  INPUT-QUEUE-NAME       PIC X(48).
       01  ERROR-QUEUE-NAME       PIC X(48) VALUE SPACES.
       01  REPLY-QUEUE-NAME       PIC X(48) VALUE 'SAMP.REPLY'.
       01  MQ-HCONN               PIC S9(9) BINARY.
       01  MQ-HOBJ                PIC S9(9) BINARY.
       01  INPUT-HANDLE           PIC S9(9) BINARY.
       01  ERROR-HANDLE           PIC S9(9) BINARY.
       01  MQ-OPTIONS             PIC S9(9) BINARY.
       01  MQ-MD                  PIC X(324).
       01  MQ-MO                  PIC X(100).
       01  MQ-BUFLEN              PIC S9(9) BINARY.
       01  MQ-BUFFER              PIC X(1000).
       01  MQ-DATALEN             PIC S9(9) BINARY.
       01  MQ-CC                  PIC S9(9) BINARY.
       01  MQ-RC                  PIC S9(9) BINARY.
       LINKAGE SECTION.
       01  TRIGGER-QNAME          PIC X(48).
       PROCEDURE DIVISION.
       1000-OPEN-INPUT.
           MOVE TRIGGER-QNAME TO INPUT-QUEUE-NAME
           MOVE INPUT-QUEUE-NAME TO MQOD-OBJECTNAME OF MQ-OD
           CALL 'MQOPEN' USING MQ-HCONN MQ-OD MQ-OPTIONS MQ-HOBJ
                               MQ-CC MQ-RC
           IF MQ-CC = 0
               MOVE MQ-HOBJ TO INPUT-HANDLE
           END-IF.
       1100-OPEN-ERROR.
           MOVE 'SAMP.ERROR' TO ERROR-QUEUE-NAME
           MOVE ERROR-QUEUE-NAME TO MQOD-OBJECTNAME OF MQ-OD
           CALL 'MQOPEN' USING MQ-HCONN MQ-OD MQ-OPTIONS MQ-HOBJ
                               MQ-CC MQ-RC
           MOVE MQ-HOBJ TO ERROR-HANDLE.
       2000-GET.
           MOVE INPUT-HANDLE TO MQ-HOBJ
           CALL 'MQGET' USING MQ-HCONN MQ-HOBJ MQ-MD MQ-MO MQ-BUFLEN
                              MQ-BUFFER MQ-DATALEN MQ-CC MQ-RC.
       3000-PUT-ERROR.
           CALL 'MQPUT' USING MQ-HCONN ERROR-HANDLE MQ-MD MQ-MO
                              MQ-BUFLEN MQ-BUFFER MQ-CC MQ-RC.
       4000-REPLY.
           MOVE REPLY-QUEUE-NAME TO MQOD-OBJECTNAME OF MQM-OD-REPLY
           CALL 'MQPUT1' USING MQ-HCONN MQM-OD-REPLY MQ-MD MQ-MO
                               MQ-BUFLEN MQ-BUFFER MQ-CC MQ-RC
           GOBACK.
