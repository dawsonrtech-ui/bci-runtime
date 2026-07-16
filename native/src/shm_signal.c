#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "shm_signal.h"
#include <stddef.h>

EXPORT_SIG os_signal_t create_os_signal(const char* name) {
    if (!name) return NULL;
#ifdef _WIN32
    return CreateEventA(NULL, FALSE, FALSE, name);
#else
    sem_t* s = sem_open(name, O_CREAT, 0666, 0);
    return (s == SEM_FAILED) ? NULL : s;
#endif
}

EXPORT_SIG os_signal_t open_os_signal(const char* name) {
    if (!name) return NULL;
#ifdef _WIN32
    return OpenEventA(EVENT_MODIFY_STATE | SYNCHRONIZE, FALSE, name);
#else
    sem_t* s = sem_open(name, 0);
    return (s == SEM_FAILED) ? NULL : s;
#endif
}

EXPORT_SIG void trigger_os_signal(os_signal_t sig) {
    if (!sig) return;
#ifdef _WIN32
    SetEvent(sig);
#else
    sem_post(sig);
#endif
}

EXPORT_SIG int wait_os_signal(os_signal_t sig, int timeout_ms) {
    if (!sig) return -1;
#ifdef _WIN32
    DWORD ms = (timeout_ms < 0) ? INFINITE : (DWORD)timeout_ms;
    DWORD res = WaitForSingleObject(sig, ms);
    return (res == WAIT_OBJECT_0) ? 0 : -1;
#else
    if (timeout_ms < 0) {
        return sem_wait(sig);
    }
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    ts.tv_sec += timeout_ms / 1000;
    ts.tv_nsec += (timeout_ms % 1000) * 1000000L;
    if (ts.tv_nsec >= 1000000000L) {
        ts.tv_sec += 1;
        ts.tv_nsec -= 1000000000L;
    }
    return sem_timedwait(sig, &ts);
#endif
}

EXPORT_SIG void close_os_signal(os_signal_t sig, const char* name) {
    if (!sig) return;
#ifdef _WIN32
    CloseHandle(sig);
#else
    sem_close(sig);
    if (name) sem_unlink(name);
#endif
}
