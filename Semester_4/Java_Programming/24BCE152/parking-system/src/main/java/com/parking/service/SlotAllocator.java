package com.parking.service;

import com.parking.model.ParkingSlot;
import com.parking.model.Vehicle;
import com.parking.model.VehicleType;

import java.util.Comparator;
import java.util.List;
import java.util.Optional;

// Dynamic Method Dispatch - polymorphic slot allocation strategies
public abstract class SlotAllocator {
    // Template method pattern - subclasses override findBestSlot
    public Optional<ParkingSlot> allocate(List<ParkingSlot> slots, Vehicle vehicle) {
        return findBestSlot(slots, vehicle);
    }

    // Polymorphic method - overridden by subclasses (Dynamic Method Dispatch)
    protected abstract Optional<ParkingSlot> findBestSlot(List<ParkingSlot> slots, Vehicle vehicle);

    // Factory method - returns appropriate allocator based on vehicle type
    public static SlotAllocator getFor(VehicleType type) {
        return switch (type) {
            case ELECTRIC_CAR -> new EVSlotAllocator();
            case HANDICAPPED -> new HandicappedSlotAllocator();
            case MOTORCYCLE -> new NearestExitAllocator();
            case TRUCK -> new LargeSlotAllocator();
            default -> new NearestExitAllocator();
        };
    }
}

// Prefers EV charging slots, falls back to regular
class EVSlotAllocator extends SlotAllocator {
    @Override
    protected Optional<ParkingSlot> findBestSlot(List<ParkingSlot> slots, Vehicle vehicle) {
        // First try EV charging slots
        Optional<ParkingSlot> evSlot = slots.stream()
                .filter(s -> s.isAvailable() && s.isEVCharging() && s.canFit(vehicle))
                .min(Comparator.comparingInt(ParkingSlot::getFloor));

        if (evSlot.isPresent()) return evSlot;

        // Fallback: any medium/large slot (without EV restriction)
        return slots.stream()
                .filter(ParkingSlot::isAvailable)
                .filter(s -> s.getSize() != ParkingSlot.SlotSize.SMALL)
                .min(Comparator.comparingInt(ParkingSlot::getFloor));
    }
}

// Prefers handicapped spots near entrance
class HandicappedSlotAllocator extends SlotAllocator {
    @Override
    protected Optional<ParkingSlot> findBestSlot(List<ParkingSlot> slots, Vehicle vehicle) {
        Optional<ParkingSlot> hSlot = slots.stream()
                .filter(s -> s.isAvailable() && s.isHandicapped())
                .min(Comparator.comparingInt(ParkingSlot::getFloor));

        if (hSlot.isPresent()) return hSlot;

        // Fallback to any available ground floor slot
        return slots.stream()
                .filter(ParkingSlot::isAvailable)
                .filter(s -> s.getFloor() == 0)
                .findFirst();
    }
}

// Parks as close to exit as possible (lowest floor, lowest slot number)
class NearestExitAllocator extends SlotAllocator {
    @Override
    protected Optional<ParkingSlot> findBestSlot(List<ParkingSlot> slots, Vehicle vehicle) {
        return slots.stream()
                .filter(s -> s.isAvailable() && s.canFit(vehicle))
                .min(Comparator.comparingInt(ParkingSlot::getFloor)
                        .thenComparingInt(ParkingSlot::getSlotNumber));
    }
}

// Finds largest available slot for trucks
class LargeSlotAllocator extends SlotAllocator {
    @Override
    protected Optional<ParkingSlot> findBestSlot(List<ParkingSlot> slots, Vehicle vehicle) {
        return slots.stream()
                .filter(s -> s.isAvailable() && s.getSize() == ParkingSlot.SlotSize.LARGE)
                .min(Comparator.comparingInt(ParkingSlot::getFloor));
    }
}
