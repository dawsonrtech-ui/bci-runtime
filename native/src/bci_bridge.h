#ifndef BCI_BRIDGE_H
#define BCI_BRIDGE_H

#ifdef __cplusplus
extern "C" {
#endif

#if defined(_WIN32) || defined(_WIN64)
    #define EXPORT_API __declspec(dllexport)
#else
    #define EXPORT_API __attribute__((visibility("default")))
#endif

#define BCI_MAX_CHANNELS      16
#define BCI_TANGENT_DIM       136
#define BCI_STATE_NAME_LEN    16
#define BCI_OUT_JSON_SIZE     5120
#define BCI_FRAME_VERSION     3
#define BCI_GUSTATION_NUM     5

typedef struct {
    int    version;
    int    frame_count;
    int    n_tangent;
    double tangent[BCI_TANGENT_DIM];
    int    predicted_action;
    double confidence;
    char   engine_state[BCI_STATE_NAME_LEN];

    // Camera rig transform
    double camera_pos_x;
    double camera_pos_y;
    double camera_pos_z;
    double camera_fov;

    // Acoustic geometry
    int    spatial_nodes;
    double dsp_gain;
    double dsp_pan;
    double dsp_occlusion;

    // Somatosensory
    double collision_impulse;
    double thermal_target_c;

    // Olfactory
    double intensity;
    unsigned int bulb_address;

    // Gustation (sweet, salty, sour, bitter, umami)
    double gustation[BCI_GUSTATION_NUM];

    // Motor gate safety
    int    motor_gating_active;
    int    in_high_stimulus;
    int    force_zero;
} BciBridgeFrame;

// Serialize a BciBridgeFrame to a JSON string in the output buffer.
// Returns number of bytes written (excluding null), or negative on error.
EXPORT_API int bci_serialize_frame(const BciBridgeFrame* frame,
                                    char* out, int max_len);

// Build a BciBridgeFrame from raw inputs (convenience for Python ctypes).
// Returns 0 on success, -1 on error.
EXPORT_API int bci_build_frame(BciBridgeFrame* frame,
                                int frame_count, const double* tangent,
                                int n_tangent, int predicted_action,
                                double confidence, const char* engine_state);

// Validate frame fields, return 0 if valid, -1 if invalid.
EXPORT_API int bci_validate_frame(const BciBridgeFrame* frame);

// Version string.
EXPORT_API const char* bci_bridge_version(void);

#ifdef __cplusplus
}
#endif

#endif
