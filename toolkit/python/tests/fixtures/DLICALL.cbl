       IDENTIFICATION DIVISION.
       PROGRAM-ID. DLICALL.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  FUNC-CODES.
           05 FUNC-GU             PIC X(04) VALUE 'GU  '.
           05 FUNC-GHU            PIC X(04) VALUE 'GHU '.
           05 FUNC-GHN            PIC X(04) VALUE 'GHN '.
           05 FUNC-REPL           PIC X(04) VALUE 'REPL'.
           05 FUNC-ISRT           PIC X(04) VALUE 'ISRT'.
           05 FUNC-CHKP           PIC X(04) VALUE 'CHKP'.
           05 PARMCOUNT           PIC S9(05) VALUE +4 COMP-5.
       01  CUST-QUAL-SSA.
           05 FILLER              PIC X(09) VALUE 'CUSTROOT('.
           05 FILLER              PIC X(10) VALUE 'CUSTID   ='.
           05 SSA-KEY             PIC 9(08).
           05 FILLER              PIC X(01) VALUE ')'.
       01  CUST-UNQUAL-SSA        PIC X(09) VALUE 'CUSTROOT '.
       01  ORDER-SSA              PIC X(09) VALUE 'ORDERSEG '.
       01  WS-FUNC                PIC X(04).
       01  CUST-REC               PIC X(100).
       01  ORDER-REC              PIC X(200).
       01  MSG-REC                PIC X(80).
       LINKAGE SECTION.
       01  IOPCB                  PIC X(40).
       01  CUSTPCB                PIC X(40).
       PROCEDURE DIVISION.
       1000-READ-CUSTOMER.
           CALL 'CBLTDLI' USING FUNC-GU IOPCB MSG-REC
           CALL 'CBLTDLI' USING FUNC-GHU CUSTPCB CUST-REC
                                CUST-QUAL-SSA
           CALL 'CBLTDLI' USING PARMCOUNT FUNC-GHN CUSTPCB
                                ORDER-REC CUST-UNQUAL-SSA ORDER-SSA.
       2000-UPDATE-CUSTOMER.
           CALL 'CBLTDLI' USING FUNC-REPL CUSTPCB CUST-REC
           MOVE 'DLET' TO WS-FUNC
           CALL 'CBLTDLI' USING WS-FUNC CUSTPCB ORDER-REC
           CALL 'CBLTDLI' USING FUNC-ISRT IOPCB MSG-REC
           CALL 'CBLTDLI' USING FUNC-CHKP IOPCB WS-FUNC
           GOBACK.
