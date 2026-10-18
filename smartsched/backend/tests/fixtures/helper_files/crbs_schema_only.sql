-- classroombookings schema (synthetic, structure only; no rows, no people)
CREATE TABLE `bookings` (`booking_id` int NOT NULL, `room_id` int NOT NULL, `period_id` int NOT NULL);
CREATE TABLE `rooms` (`room_id` int NOT NULL, `name` varchar(20) NOT NULL);
CREATE TABLE `periods` (`period_id` int NOT NULL, `time_start` time NOT NULL);
CREATE TABLE `weeks` (`week_id` int NOT NULL, `name` varchar(20) NOT NULL);
CREATE TABLE `sessions` (`session_id` int NOT NULL, `name` varchar(50) NOT NULL);
CREATE TABLE `holidays` (`holiday_id` int NOT NULL, `date_start` date NOT NULL);
CREATE TABLE `departments` (`department_id` int NOT NULL, `name` varchar(50) NOT NULL);
