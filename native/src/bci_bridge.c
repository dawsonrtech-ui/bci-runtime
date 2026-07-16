#include "bci_bridge.h"
#include <stdio.h>
#include <string.h>
#include <math.h>

static const char* _version = "bci-bridge/2.1.0";

EXPORT_API const char* bci_bridge_version(void) {
    return _version;
}

EXPORT_API int bci_validate_frame(const BciBridgeFrame* frame) {
    if (!frame) return -1;
    if (frame->version != BCI_FRAME_VERSION) return -1;
    if (frame->frame_count < 0) return -1;
    if (frame->n_tangent < 0 || frame->n_tangent > BCI_TANGENT_DIM) return -1;
    if (frame->predicted_action < 0) return -1;
    if (frame->confidence < 0.0 || frame->confidence > 1.0) return -1;
    return 0;
}

EXPORT_API int bci_build_frame(BciBridgeFrame* frame,
                                int frame_count, const double* tangent,
                                int n_tangent, int predicted_action,
                                double confidence, const char* engine_state) {
    if (!frame || !tangent || !engine_state) return -1;
    if (n_tangent > BCI_TANGENT_DIM) return -1;

    memset(frame, 0, sizeof(BciBridgeFrame));
    frame->version = BCI_FRAME_VERSION;
    frame->frame_count = frame_count;
    frame->n_tangent = n_tangent;
    frame->predicted_action = predicted_action;
    frame->confidence = confidence;
    frame->motor_gating_active = 1;
    frame->in_high_stimulus = 0;
    frame->force_zero = 0;
    frame->spatial_nodes = 64;
    frame->dsp_gain = 1.0;
    frame->thermal_target_c = 22.0;

    for (int i = 0; i < n_tangent; ++i) {
        frame->tangent[i] = tangent[i];
    }

    strncpy(frame->engine_state, engine_state, BCI_STATE_NAME_LEN - 1);
    frame->engine_state[BCI_STATE_NAME_LEN - 1] = '\0';

    return 0;
}

EXPORT_API int bci_serialize_frame(const BciBridgeFrame* frame,
                                    char* out, int max_len) {
    if (!frame || !out || max_len < 64) return -1;

    int pos = 0;
    int n;

    n = snprintf(out + pos, max_len - pos,
        "{\"v\":%d,\"f\":%d,\"s\":\"%s\",\"a\":%d,\"c\":%.6f,",
        frame->version,
        frame->frame_count,
        frame->engine_state,
        frame->predicted_action,
        frame->confidence);
    if (n < 0 || n >= max_len - pos) return -1;
    pos += n;

    // Tangent vector
    n = snprintf(out + pos, max_len - pos, "\"t\":[");
    if (n < 0 || n >= max_len - pos) return -1;
    pos += n;
    for (int i = 0; i < frame->n_tangent; ++i) {
        if (i > 0) {
            n = snprintf(out + pos, max_len - pos, ",");
            if (n < 0 || n >= max_len - pos) return -1;
            pos += n;
        }
        n = snprintf(out + pos, max_len - pos, "%.10f", frame->tangent[i]);
        if (n < 0 || n >= max_len - pos) return -1;
        pos += n;
    }
    n = snprintf(out + pos, max_len - pos, "],");
    if (n < 0 || n >= max_len - pos) return -1;
    pos += n;

    // Camera rig
    n = snprintf(out + pos, max_len - pos,
        "\"cam\":[%.2f,%.2f,%.2f,%.1f],",
        frame->camera_pos_x,
        frame->camera_pos_y,
        frame->camera_pos_z,
        frame->camera_fov);
    if (n < 0 || n >= max_len - pos) return -1;
    pos += n;

    // Acoustic geometry
    n = snprintf(out + pos, max_len - pos,
        "\"audio\":{\"n\":%d,\"g\":%.3f,\"p\":%.3f,\"o\":%.3f},",
        frame->spatial_nodes,
        frame->dsp_gain,
        frame->dsp_pan,
        frame->dsp_occlusion);
    if (n < 0 || n >= max_len - pos) return -1;
    pos += n;

    // Collision impulse + thermal
    n = snprintf(out + pos, max_len - pos,
        "\"impact\":{\"i\":%.6f,\"t\":%.1f},",
        frame->collision_impulse,
        frame->thermal_target_c);
    if (n < 0 || n >= max_len - pos) return -1;
    pos += n;

    // Olfactory
    n = snprintf(out + pos, max_len - pos,
        "\"olf\":{\"addr\":\"0x%04X\",\"int\":%.3f},",
        frame->bulb_address,
        frame->intensity);
    if (n < 0 || n >= max_len - pos) return -1;
    pos += n;

    // Gustation
    n = snprintf(out + pos, max_len - pos, "\"gust\":[");
    if (n < 0 || n >= max_len - pos) return -1;
    pos += n;
    for (int i = 0; i < BCI_GUSTATION_NUM; ++i) {
        if (i > 0) {
            n = snprintf(out + pos, max_len - pos, ",");
            if (n < 0 || n >= max_len - pos) return -1;
            pos += n;
        }
        n = snprintf(out + pos, max_len - pos, "%.4f", frame->gustation[i]);
        if (n < 0 || n >= max_len - pos) return -1;
        pos += n;
    }
    n = snprintf(out + pos, max_len - pos, "],");
    if (n < 0 || n >= max_len - pos) return -1;
    pos += n;

    // Motor gate safety
    n = snprintf(out + pos, max_len - pos,
        "\"mg\":{\"act\":%d,\"stim\":%d,\"fz\":%d}",
        frame->motor_gating_active,
        frame->in_high_stimulus,
        frame->force_zero);
    if (n < 0 || n >= max_len - pos) return -1;
    pos += n;

    // Close
    n = snprintf(out + pos, max_len - pos, "}");
    if (n < 0 || n >= max_len - pos) return -1;
    pos += n;

    return pos;
}
