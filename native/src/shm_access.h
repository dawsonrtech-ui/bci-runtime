#ifndef SHM_ACCESS_H
#define SHM_ACCESS_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

#if defined(_WIN32) || defined(_WIN64)
    #include <windows.h>
    typedef HANDLE shm_handle_t;
    #define EXPORT_SHM __declspec(dllexport)
#else
    #include <sys/mman.h>
    #include <fcntl.h>
    #include <unistd.h>
    typedef int shm_handle_t;
    #define EXPORT_SHM __attribute__((visibility("default")))
#endif

// Open or create a named shared memory region.
// Returns handle (non-zero on success, 0/NULL on failure).
EXPORT_SHM shm_handle_t open_shm(const char* name, int size, int create);

// Map shared memory into process address space.
// Returns pointer, or NULL on failure.
EXPORT_SHM void* map_shm(shm_handle_t handle, int size);

// Unmap shared memory.
EXPORT_SHM void unmap_shm(void* ptr, int size);

// Close shared memory handle. If destroy is non-zero, unlink the name.
EXPORT_SHM void close_shm(shm_handle_t handle, const char* name, int destroy);

#ifdef __cplusplus
}
#endif

#endif
