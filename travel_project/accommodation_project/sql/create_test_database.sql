/*
Run this script in SSMS while connected to:
DESKTOP-KIUBV7G\SQLEXPRESS01

It creates a separate local database for development/testing.
It does not alter the original AccommodationDB database.
*/

USE [master];
GO

IF DB_ID(N'AccommodationDB_Test') IS NULL
BEGIN
    CREATE DATABASE [AccommodationDB_Test];
END
GO

ALTER DATABASE [AccommodationDB_Test] SET RECOVERY SIMPLE;
GO

SELECT
    name,
    database_id,
    create_date
FROM sys.databases
WHERE name = N'AccommodationDB_Test';
GO
