/*
 * Copyright (c) 2026 Amp.
 *
 * This program and the accompanying materials are made
 * available under the terms of the Eclipse Public License 2.0
 * which is available at https://www.eclipse.org/legal/epl-2.0/
 *
 * SPDX-License-Identifier: EPL-2.0
 *
 * Contributors:
 *    Amp - verify the tables, keys, indexes and views read from DDL
 *
 */
package org.eclipse.lsp.cobol.cli.command;

import static org.junit.jupiter.api.Assertions.assertEquals;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import org.junit.jupiter.api.Test;

/**
 * Reads a Db2 DDL file wrapped in JCL, as many repositories keep it, with a sequence number on one
 * line, a long line whose columns 73 onwards are SQL, and older Db2 for z/OS forms: a constraint
 * name after FOREIGN KEY and ERASE without USING.
 */
class CliDdlTest {
  private static final String DDL =
      "//CREATE   JOB (ACCT),'DDL'\n"
          + "//SYSTSIN  DD *\n"
          + " DSN SYSTEM(DB2A)\n"
          + " RUN PROGRAM(DSNTIAD) PLAN(DSNTIA13)\n"
          + "//SYSIN    DD *\n"
          + "-- customers\n"
          + "CREATE TABLE BANK.CUSTOMER (\n"
          + "  CUST_ID   CHAR(10) NOT NULL,\n"
          + "  NAME      VARCHAR(40),\n"
          + "  OPENED    DATE NOT NULL WITH DEFAULT,                                 00000100\n"
          + "  PRIMARY KEY (CUST_ID)\n"
          + ") IN BANKDB.CUSTTS;\n"
          + "CREATE TABLE ACCOUNT (\n"
          + "  ACCT_NO   CHAR(8) NOT NULL,\n"
          + "  CUST_ID   CHAR(10) NOT NULL,\n"
          + "  BALANCE   DECIMAL(12, 2),\n"
          + "  CONSTRAINT ACCT_PK PRIMARY KEY (ACCT_NO),\n"
          + "  FOREIGN KEY ACCT_CUST (CUST_ID) REFERENCES BANK.CUSTOMER (CUST_ID) ON DELETE CASCADE\n"
          + ");\n"
          + "CREATE UNIQUE INDEX ACCT_IX ON ACCOUNT (CUST_ID ASC, ACCT_NO) ERASE NO CLOSE NO;\n"
          + "ALTER TABLE ACCOUNT ADD COLUMN STATUS CHAR(1);\n"
          + "CREATE VIEW RICH AS SELECT C.NAME FROM BANK.CUSTOMER C, ACCOUNT A\n"
          + "  WHERE C.CUST_ID = A.CUST_ID AND A.BALANCE > 1000;\n"
          + "GRANT SELECT ON ACCOUNT TO PUBLIC;\n"
          + "CREATE PROCEDURE PURGE () LANGUAGE SQL BEGIN DELETE FROM ACCOUNT; END#\n"
          + "CREATE TABLE BROKEN (A CHAR(1) NOT NOT NULL);\n";

  @Test
  void readsTablesKeysIndexesAndViews() {
    JsonObject result = CliDdl.describe(DDL);
    JsonArray objects = result.getAsJsonArray("objects");
    assertEquals(5, objects.size());

    JsonObject customer = objects.get(0).getAsJsonObject();
    assertEquals("TABLE", customer.get("kind").getAsString());
    assertEquals("BANK.CUSTOMER", customer.get("name").getAsString());
    assertEquals(7, customer.get("line").getAsInt());
    JsonArray columns = customer.getAsJsonArray("columns");
    assertEquals(3, columns.size());
    assertEquals("CHAR(10)", columns.get(0).getAsJsonObject().get("type").getAsString());
    assertEquals(true, columns.get(0).getAsJsonObject().get("notNull").getAsBoolean());
    assertEquals(false, columns.get(1).getAsJsonObject().get("notNull").getAsBoolean());
    assertEquals("WITH DEFAULT", columns.get(2).getAsJsonObject().get("default").getAsString());
    assertEquals("[\"CUST_ID\"]", customer.get("primaryKey").toString());

    JsonObject account = objects.get(1).getAsJsonObject();
    assertEquals("DECIMAL(12, 2)", account.getAsJsonArray("columns").get(2).getAsJsonObject().get("type").getAsString());
    assertEquals("[\"ACCT_NO\"]", account.get("primaryKey").toString());
    JsonObject fk = account.getAsJsonArray("foreignKeys").get(0).getAsJsonObject();
    assertEquals("[\"CUST_ID\"]", fk.get("columns").toString());
    assertEquals("BANK.CUSTOMER", fk.get("references").getAsString());
    assertEquals("[\"CUST_ID\"]", fk.get("referencedColumns").toString());
    assertEquals("CASCADE", fk.get("onDelete").getAsString());

    JsonObject index = objects.get(2).getAsJsonObject();
    assertEquals("INDEX", index.get("kind").getAsString());
    assertEquals(true, index.get("unique").getAsBoolean());
    assertEquals("ACCOUNT", index.get("table").getAsString());
    assertEquals("[\"CUST_ID ASC\",\"ACCT_NO\"]", index.get("columns").toString());

    JsonObject alter = objects.get(3).getAsJsonObject();
    assertEquals("ALTER TABLE", alter.get("kind").getAsString());
    assertEquals("STATUS", alter.getAsJsonArray("columns").get(0).getAsJsonObject().get("name").getAsString());

    JsonObject view = objects.get(4).getAsJsonObject();
    assertEquals("RICH", view.get("name").getAsString());
    assertEquals("[\"BANK.CUSTOMER\",\"ACCOUNT\"]", view.get("tables").toString());

    assertEquals(2, result.get("otherStatements").getAsInt());
    JsonArray errors = result.getAsJsonArray("errors");
    assertEquals(1, errors.size());
    assertEquals(26, errors.get(0).getAsJsonObject().get("line").getAsInt());
    assertEquals(
        "line 26: mismatched input 'NOT' expecting {',', ')', ', '}",
        errors.get(0).getAsJsonObject().get("message").getAsString());
  }
}
