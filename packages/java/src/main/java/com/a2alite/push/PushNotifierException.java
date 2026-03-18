package com.a2alite.push;

/**
 * Thrown when a push notification cannot be delivered.
 */
public class PushNotifierException extends RuntimeException {

    public PushNotifierException(String message) {
        super(message);
    }

    public PushNotifierException(String message, Throwable cause) {
        super(message, cause);
    }
}
