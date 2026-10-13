package com.parking.util;

import java.io.*;
import java.nio.file.*;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;

// File Handling concept - Persistent logging to disk
public class FileLogger {
    private static final DateTimeFormatter FORMATTER = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
    private final String logFilePath;
    private BufferedWriter writer;
    private final Object lock = new Object(); // For thread-safe file writes

    public FileLogger(String filename) {
        this.logFilePath = filename;
        try {
            // File handling: open in append mode
            writer = new BufferedWriter(new FileWriter(logFilePath, true));
            log("SYSTEM", "=== Parking System Started ===");
        } catch (IOException e) {
            System.err.println("Warning: Could not open log file: " + e.getMessage());
        }
    }

    // Thread-safe logging - Multithreading concept applied to file I/O
    public void log(String event, String message) {
        String entry = String.format("[%s] [%s] %s%n",
                LocalDateTime.now().format(FORMATTER), event, message);

        synchronized (lock) {
            try {
                if (writer != null) {
                    writer.write(entry);
                    writer.flush();
                }
            } catch (IOException e) {
                System.err.println("Log write error: " + e.getMessage());
            }
        }
        System.out.print(entry); // Also print to console
    }

    // Read log file contents
    public List<String> readLogs(int lastNLines) {
        List<String> lines = new ArrayList<>();
        try {
            Path path = Paths.get(logFilePath);
            if (Files.exists(path)) {
                List<String> allLines = Files.readAllLines(path);
                int start = Math.max(0, allLines.size() - lastNLines);
                lines = allLines.subList(start, allLines.size());
            }
        } catch (IOException e) {
            lines.add("Error reading logs: " + e.getMessage());
        }
        return lines;
    }

    public void close() {
        synchronized (lock) {
            try {
                if (writer != null) {
                    log("SYSTEM", "=== Parking System Shutting Down ===");
                    writer.close();
                }
            } catch (IOException e) {
                System.err.println("Error closing log file: " + e.getMessage());
            }
        }
    }
}
