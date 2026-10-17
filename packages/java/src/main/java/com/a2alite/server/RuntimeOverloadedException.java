package com.a2alite.server;

/** Admission is rejected before SDK resources are allocated. */
final class RuntimeOverloadedException extends RuntimeException {
    RuntimeOverloadedException() {
        super("Runtime capacity unavailable");
    }
}
