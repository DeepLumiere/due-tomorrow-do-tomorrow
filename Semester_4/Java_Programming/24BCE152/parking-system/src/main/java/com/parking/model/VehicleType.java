package com.parking.model;

public enum VehicleType {
    MOTORCYCLE("Motorcycle", "🏍️"),
    CAR("Car", "🚗"),
    TRUCK("Truck", "🚚"),
    ELECTRIC_CAR("Electric Car", "⚡"),
    HANDICAPPED("Handicapped", "♿");

    private final String displayName;
    private final String icon;

    VehicleType(String displayName, String icon) {
        this.displayName = displayName;
        this.icon = icon;
    }

    public String getDisplayName() { return displayName; }
    public String getIcon() { return icon; }
}
