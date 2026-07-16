# Project Synapse — Native C++ Core Cross-Compilation Makefile
# Targets match the Post-Merger Integration Roadmap (Phase 5)
#
# Usage:
#   make <target>     — build for a specific platform
#   make all          — build all targets (requires all toolchains)
#   make clean        — remove all build artifacts

SRC := src/bci_core.cpp
BRIDGE_SRC := src/bci_bridge.c
SIGNAL_SRC := src/shm_signal.c
SHM_ACCESS_SRC := src/shm_access.c
BUILD_DIR := build

# Default target: host native
.PHONY: default
default: host

# ─── Host (developer machine) ────────────────────────────────────

.PHONY: host
host: $(BUILD_DIR)/libbci_core.so $(BUILD_DIR)/bci_core.dll \
      $(BUILD_DIR)/libbci_bridge.so $(BUILD_DIR)/bci_bridge.dll

$(BUILD_DIR)/libbci_core.so: $(SRC) | $(BUILD_DIR)
	g++ -O3 -fPIC -shared -std=c++17 -fopenmp \
		$< -o $@

$(BUILD_DIR)/bci_core.dll: $(SRC) | $(BUILD_DIR)
	cl /O2 /std:c++17 /W4 /WX /LD /openmp \
		$< /Fe$@

$(BUILD_DIR)/libbci_bridge.so: $(BRIDGE_SRC) $(SIGNAL_SRC) $(SHM_ACCESS_SRC) | $(BUILD_DIR)
	gcc -O3 -fPIC -shared -std=c11 -lrt \
		$(BRIDGE_SRC) $(SIGNAL_SRC) $(SHM_ACCESS_SRC) -o $@ -lm -lpthread

$(BUILD_DIR)/bci_bridge.dll: $(BRIDGE_SRC) $(SIGNAL_SRC) $(SHM_ACCESS_SRC) | $(BUILD_DIR)
	cl /O2 /std:c17 /W4 /WX /LD \
		$(BRIDGE_SRC) $(SIGNAL_SRC) $(SHM_ACCESS_SRC) /Fe$@

# ─── Bridge-only targets (for CI wheel build) ───────────────────

.PHONY: libbci_bridge.so
libbci_bridge.so: $(BUILD_DIR)/libbci_bridge.so

.PHONY: bci_bridge.dll
bci_bridge.dll: $(BUILD_DIR)/bci_bridge.dll

# ─── Linux x64 (CI / Docker runtime) ────────────────────────────

LB_TARGETS := linux-amd64
linux-amd64: $(BUILD_DIR)/linux-amd64/libbci_core.so

$(BUILD_DIR)/linux-amd64/libbci_core.so: $(SRC) | $(BUILD_DIR)/linux-amd64
	x86_64-linux-gnu-g++ -O3 -fPIC -shared -std=c++17 -fopenmp \
		$< -o $@

# ─── Android ARM64 (Meta Quest / Standalone XR) ─────────────────

LB_TARGETS += android-arm64
android-arm64: $(BUILD_DIR)/android-arm64/libbci_core.so

$(BUILD_DIR)/android-arm64/libbci_core.so: $(SRC) | $(BUILD_DIR)/android-arm64
	aarch64-linux-android21-g++ -O3 -fPIC -shared -std=c++17 \
		-static-libstdc++ $< -o $@

# ─── Apple Vision Pro (visionOS / Apple Silicon ARM64) ──────────

LB_TARGETS += visionos-arm64
visionos-arm64: $(BUILD_DIR)/visionos-arm64/libbci_core.dylib

$(BUILD_DIR)/visionos-arm64/libbci_core.dylib: $(SRC) | $(BUILD_DIR)/visionos-arm64
	xcrun --sdk xros clang++ -O3 -dynamiclib -arch arm64 -std=c++17 \
		-isysroot /Applications/Xcode.app/Contents/Developer/Platforms/XROS.platform/Developer/SDKs/XROS.sdk \
		$< -o $@

# ─── macOS ARM64 (local dev / testing) ──────────────────────────

LB_TARGETS += macos-arm64
macos-arm64: $(BUILD_DIR)/macos-arm64/libbci_core.dylib

$(BUILD_DIR)/macos-arm64/libbci_core.dylib: $(SRC) | $(BUILD_DIR)/macos-arm64
	clang++ -O3 -dynamiclib -arch arm64 -std=c++17 -fopenmp \
		$< -o $@

# ─── All ─────────────────────────────────────────────────────────

.PHONY: all
all: host $(LB_TARGETS)

# ─── Clean ───────────────────────────────────────────────────────

.PHONY: clean
clean:
	rm -rf $(BUILD_DIR)

# ─── Directory scaffolding ───────────────────────────────────────

$(BUILD_DIR):
	mkdir -p $@

$(BUILD_DIR)/linux-amd64 $(BUILD_DIR)/android-arm64 \
$(BUILD_DIR)/visionos-arm64 $(BUILD_DIR)/macos-arm64:
	mkdir -p $@
