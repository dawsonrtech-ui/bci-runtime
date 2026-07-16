#ifndef SHM_SIGNAL_H
#define SHM_SIGNAL_H

#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif

#ifdef __cplusplus
extern "C" {
#endif

#if defined(_WIN32) || defined(_WIN64)
    #include <windows.h>
    typedef HANDLE os_signal_t;
    #define EXPORT_SIG __declspec(dllexport)
#else
    #include <semaphore.h>
    #include <fcntl.h>
    #include <time.h>
    typedef sem_t* os_signal_t;
    #define EXPORT_SIG __attribute__((visibility("default")))
#endif

// Create a named signal object (auto-reset on Windows, semaphore on POSIX).
// Returns NULL on failure.
EXPORT_SIG os_signal_t create_os_signal(const char* name);

// Open an existing named signal object created by another process.
EXPORT_SIG os_signal_t open_os_signal(const char* name);

// Signal/Post — set the event to signaled state / increment semaphore.
EXPORT_SIG void trigger_os_signal(os_signal_t sig);

// Wait on the signal with an optional timeout in milliseconds.
// timeout_ms = -1 means block indefinitely.
// Returns 0 on signaled, -1 on timeout or error.
EXPORT_SIG int wait_os_signal(os_signal_t sig, int timeout_ms);

// Close/destroy the signal handle.
// On POSIX, if name is non-NULL, sem_unlink is called.
EXPORT_SIG void close_os_signal(os_signal_t sig, const char* name);

#ifdef __cplusplus
}
#endif

#endif
