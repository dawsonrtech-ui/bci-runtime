#ifndef SHM_DEFS_H
#define SHM_DEFS_H

#include <stdint.h>

#define RING_BUFFER_SIZE          32
#define MAX_CHANNELS_PER_FRAME    16

// Exact binary layout shared across C, Python (ctypes), and Unity (C#)
// Packed at 4-byte boundary to prevent ABI divergence between compilers.
#pragma pack(push, 4)

typedef struct {
    uint32_t channel_id;
    float    intensity;
    float    duration_ms;
    uint8_t  chemical_profile;
    uint8_t  padding[3];
} GustationChannel;

typedef struct {
    uint32_t          packet_id;
    uint32_t          channel_count;
    GustationChannel  channels[MAX_CHANNELS_PER_FRAME];
} ShmSlot;

typedef struct {
    volatile uint64_t head;
    volatile uint64_t tail;
    ShmSlot           slots[RING_BUFFER_SIZE];
} SharedRingBuffer;

#pragma pack(pop)

// Convenience: total byte size of the shared memory block
#define SHM_TOTAL_SIZE \
    (sizeof(SharedRingBuffer))

// Bitmask for rapid slot indexing (RING_BUFFER_SIZE must be power of 2)
#define SHM_SLOT_MASK  (RING_BUFFER_SIZE - 1)

#endif
