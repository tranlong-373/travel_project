IF DB_ID('MiniSmartStayDB') IS NULL
BEGIN
    CREATE DATABASE MiniSmartStayDB;
END
GO

USE MiniSmartStayDB;
GO

IF OBJECT_ID('dbo.Accommodations', 'U') IS NOT NULL
    DROP TABLE dbo.Accommodations;
GO

CREATE TABLE dbo.Accommodations
(
    AccommodationID INT IDENTITY(1,1) PRIMARY KEY,
    Name NVARCHAR(200) NOT NULL,
    City NVARCHAR(100) NOT NULL,
    AccommodationType NVARCHAR(50) NOT NULL,
    PricePerNight DECIMAL(12,2) NOT NULL,
    Rating DECIMAL(3,2) NOT NULL,
    MaxPeople INT NOT NULL
);
GO

INSERT INTO dbo.Accommodations
(Name, City, AccommodationType, PricePerNight, Rating, MaxPeople)
VALUES
(N'Lavender Home', N'Đà Lạt', N'Homestay', 750000, 4.6, 2),
(N'Pine Hotel', N'Đà Lạt', N'Hotel', 950000, 4.4, 3),
(N'Moonlight Homestay', N'Đà Lạt', N'Homestay', 680000, 4.3, 2),
(N'Sea Light Hotel', N'Vũng Tàu', N'Hotel', 920000, 4.5, 4),
(N'Ocean View Homestay', N'Vũng Tàu', N'Homestay', 800000, 4.2, 2),
(N'Danang Sun Hostel', N'Đà Nẵng', N'Hostel', 350000, 4.1, 2),
(N'Danang Blue Hotel', N'Đà Nẵng', N'Hotel', 870000, 4.4, 3);
GO

SELECT * FROM dbo.Accommodations;
GO

SELECT *
FROM dbo.Accommodations
WHERE City = N'Đà Lạt';

