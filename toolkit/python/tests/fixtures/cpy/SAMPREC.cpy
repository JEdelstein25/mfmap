       01  SAMP-RECORD.
           05 SAMP-ID             PIC 9(9).
           05 SAMP-NAME           PIC X(30).
           05 SAMP-COUNT          PIC 99.
           05 SAMP-ITEM OCCURS 1 TO 20 DEPENDING ON SAMP-COUNT.
              10 SAMP-CODE        PIC X(2).
