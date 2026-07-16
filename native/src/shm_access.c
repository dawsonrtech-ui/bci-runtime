#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <unistd.h>
#include "shm_access.h"

shm_handle_t open_shm(const char* name, int size, int create) {
    if (!name || size <= 0) return 0;
#ifdef _WIN32
    HANDLE h = CreateFileMappingA(
        INVALID_HANDLE_VALUE, NULL,
        PAGE_READWRITE,
        0, (DWORD)size,
        name);
    return h;
#else
    int oflags = O_RDWR;
    if (create) oflags |= O_CREAT | O_EXCL;
    int fd = shm_open(name, oflags, 0666);
    if (fd < 0 && create) {
        oflags = O_RDWR | O_CREAT;
        fd = shm_open(name, oflags, 0666);
    }
    if (fd >= 0 && create) {
        ftruncate(fd, size);
    }
    return fd;
#endif
}

void* map_shm(shm_handle_t handle, int size) {
    if (!handle || size <= 0) return NULL;
#ifdef _WIN32
    return MapViewOfFile(handle, FILE_MAP_ALL_ACCESS, 0, 0, (SIZE_T)size);
#else
    return mmap(NULL, (size_t)size, PROT_READ | PROT_WRITE,
                MAP_SHARED, handle, 0);
#endif
}

void unmap_shm(void* ptr, int size) {
    if (!ptr) return;
#ifdef _WIN32
    (void)size;
    UnmapViewOfFile(ptr);
#else
    munmap(ptr, (size_t)size);
#endif
}

void close_shm(shm_handle_t handle, const char* name, int destroy) {
    if (!handle) return;
#ifdef _WIN32
    (void)name;
    (void)destroy;
    CloseHandle(handle);
#else
    close(handle);
    if (destroy && name) {
        shm_unlink(name);
    }
#endif
}
