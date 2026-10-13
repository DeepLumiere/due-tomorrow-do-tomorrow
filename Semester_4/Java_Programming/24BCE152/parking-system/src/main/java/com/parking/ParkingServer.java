package com.parking;

import com.parking.exception.ParkingException;
import com.parking.model.*;
import com.parking.service.ParkingLotService;
import com.parking.util.FileLogger;
import com.parking.util.JsonBuilder;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.*;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.stream.Collectors;

public class ParkingServer {

    private static final int PORT = 8080;
    private static ParkingLotService parkingService;
    private static FileLogger serverLogger;

    public static void main(String[] args) throws IOException {
        parkingService = ParkingLotService.getInstance();
        serverLogger = new FileLogger("server_log.txt");

        HttpServer server = HttpServer.create(new InetSocketAddress(PORT), 0);

        server.createContext("/api/checkin", ParkingServer::handleCheckIn);
        server.createContext("/api/checkout", ParkingServer::handleCheckOut);
        server.createContext("/api/find", ParkingServer::handleFind);
        server.createContext("/api/slots", ParkingServer::handleSlots);
        server.createContext("/api/stats", ParkingServer::handleStats);
        server.createContext("/api/active", ParkingServer::handleActiveTickets);
        server.createContext("/api/history", ParkingServer::handleHistory);
        server.createContext("/api/logs", ParkingServer::handleLogs);

        server.createContext("/", ParkingServer::handleStatic);

        server.setExecutor(java.util.concurrent.Executors.newFixedThreadPool(10)); // Thread pool
        server.start();

        System.out.println("╔══════════════════════════════════════╗");
        System.out.println("║   Open: http://localhost:" + PORT + "       ║");
        System.out.println("╚══════════════════════════════════════╝");

        // Shutdown hook - Exception Handling / Multithreading
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            server.stop(1);
            parkingService.shutdown();
            System.out.println("Server shut down gracefully.");
        }));
    }

    private static void handleCheckIn(HttpExchange exchange) throws IOException {
        if (!exchange.getRequestMethod().equals("POST")) {
            sendResponse(exchange, 405, JsonBuilder.error("Method not allowed", "METHOD_NOT_ALLOWED"));
            return;
        }

        try {
            Map<String, String> params = parseBody(exchange);
            String type = params.getOrDefault("vehicleType", "");
            String plate = params.getOrDefault("licensePlate", "");
            String owner = params.getOrDefault("ownerName", "");
            String phone = params.getOrDefault("ownerPhone", "");

            Vehicle vehicle = VehicleFactory.createVehicle(type, plate, owner, phone);
            ParkingTicket ticket = parkingService.checkIn(vehicle);

            String json = JsonBuilder.success(JsonBuilder.ticketToJson(ticket, vehicle));
            sendResponse(exchange, 200, json);

        } catch (ParkingException e) {
            serverLogger.log("ERROR", "CheckIn failed: " + e.getMessage());
            sendResponse(exchange, 400, JsonBuilder.error(e.getMessage(), e.getErrorCode()));
        } catch (Exception e) {
            serverLogger.log("ERROR", "Unexpected: " + e.getMessage());
            sendResponse(exchange, 500, JsonBuilder.error("Internal server error", "SERVER_ERROR"));
        }
    }

    private static void handleCheckOut(HttpExchange exchange) throws IOException {
        if (!exchange.getRequestMethod().equals("POST")) {
            sendResponse(exchange, 405, JsonBuilder.error("Method not allowed", "METHOD_NOT_ALLOWED"));
            return;
        }

        try {
            Map<String, String> params = parseBody(exchange);
            String ticketId = params.getOrDefault("ticketId", "");

            Vehicle vehicle = parkingService.getVehicleByTicketId(ticketId);
            ParkingTicket ticket = parkingService.checkOut(ticketId);

            String json = JsonBuilder.success(JsonBuilder.ticketToJson(ticket, vehicle));
            sendResponse(exchange, 200, json);

        } catch (ParkingException e) {
            sendResponse(exchange, 400, JsonBuilder.error(e.getMessage(), e.getErrorCode()));
        } catch (Exception e) {
            sendResponse(exchange, 500, JsonBuilder.error("Internal server error", "SERVER_ERROR"));
        }
    }

    private static void handleFind(HttpExchange exchange) throws IOException {
        try {
            Map<String, String> query = parseQuery(exchange.getRequestURI().getQuery());
            String plate = query.getOrDefault("plate", "");

            ParkingTicket ticket = parkingService.findTicketByLicensePlate(plate);
            Vehicle vehicle = parkingService.getVehicleByTicketId(ticket.getTicketId());

            sendResponse(exchange, 200, JsonBuilder.success(JsonBuilder.ticketToJson(ticket, vehicle)));

        } catch (ParkingException e) {
            sendResponse(exchange, 404, JsonBuilder.error(e.getMessage(), "NOT_FOUND"));
        }
    }

    private static void handleSlots(HttpExchange exchange) throws IOException {
        List<String> slotJsons = parkingService.getAllSlots().stream()
                .map(JsonBuilder::slotToJson)
                .collect(Collectors.toList());
        sendResponse(exchange, 200, JsonBuilder.success(JsonBuilder.listToJson(slotJsons)));
    }

    private static void handleStats(HttpExchange exchange) throws IOException {
        Map<String, Integer> stats = parkingService.getOccupancyStats();
        double revenue = parkingService.getTotalRevenue();
        String json = JsonBuilder.success(JsonBuilder.statsToJson(stats, revenue, parkingService.getLotName()));
        sendResponse(exchange, 200, json);
    }

    private static void handleActiveTickets(HttpExchange exchange) throws IOException {
        List<String> tickets = parkingService.getActiveTickets().stream()
                .map(t -> JsonBuilder.ticketToJson(t, parkingService.getVehicleByTicketId(t.getTicketId())))
                .collect(Collectors.toList());
        sendResponse(exchange, 200, JsonBuilder.success(JsonBuilder.listToJson(tickets)));
    }

    private static void handleHistory(HttpExchange exchange) throws IOException {
        List<String> tickets = parkingService.getCompletedTickets().stream()
                .map(t -> JsonBuilder.ticketToJson(t, null))
                .collect(Collectors.toList());
        sendResponse(exchange, 200, JsonBuilder.success(JsonBuilder.listToJson(tickets)));
    }

    private static void handleLogs(HttpExchange exchange) throws IOException {
        FileLogger logger = new FileLogger("parking_log.txt");
        List<String> logs = logger.readLogs(50);
        StringBuilder sb = new StringBuilder("[");
        for (int i = 0; i < logs.size(); i++) {
            sb.append("\"").append(logs.get(i).replace("\"", "'").replace("\n", "")).append("\"");
            if (i < logs.size() - 1) sb.append(",");
        }
        sb.append("]");
        sendResponse(exchange, 200, JsonBuilder.success(sb.toString()));
    }

    private static void handleStatic(HttpExchange exchange) throws IOException {
        String path = exchange.getRequestURI().getPath();
        if (path.equals("/") || path.equals("/index.html")) {
            File f = new File("frontend/index.html");
            if (f.exists()) {
                byte[] bytes = java.nio.file.Files.readAllBytes(f.toPath());
                exchange.getResponseHeaders().set("Content-Type", "text/html; charset=UTF-8");
                exchange.sendResponseHeaders(200, bytes.length);
                exchange.getResponseBody().write(bytes);
                exchange.getResponseBody().close();
                return;
            }
        }
        sendResponse(exchange, 404, "Not found");
    }

    // --- Utility Methods ---

    private static void sendResponse(HttpExchange exchange, int status, String body) throws IOException {
        exchange.getResponseHeaders().set("Content-Type", "application/json");
        exchange.getResponseHeaders().set("Access-Control-Allow-Origin", "*");
        exchange.getResponseHeaders().set("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
        exchange.getResponseHeaders().set("Access-Control-Allow-Headers", "Content-Type");
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream os = exchange.getResponseBody()) {
            os.write(bytes);
        }
    }

    private static Map<String, String> parseBody(HttpExchange exchange) throws IOException {
        try (InputStream is = exchange.getRequestBody()) {
            String body = new String(is.readAllBytes(), StandardCharsets.UTF_8);
            return parseQuery(body);
        }
    }

    private static Map<String, String> parseQuery(String query) {
        Map<String, String> params = new LinkedHashMap<>();
        if (query == null || query.isBlank()) return params;
        for (String pair : query.split("&")) {
            String[] kv = pair.split("=", 2);
            if (kv.length == 2) {
                try {
                    params.put(
                            URLDecoder.decode(kv[0], StandardCharsets.UTF_8),
                            URLDecoder.decode(kv[1], StandardCharsets.UTF_8)
                    );
                } catch (Exception ignored) {}
            }
        }
        return params;
    }
}
