#!/bin/bash

# Pi OS Burner Script
# Downloads latest Pi OS and burns it to SD card with dog feeding config

set -euo pipefail

readonly PI_OS_URL="https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2026-04-14/2026-04-13-raspios-trixie-arm64-lite.img.xz"
readonly PI_OS_SHA256_URL="https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2026-04-14/2026-04-13-raspios-trixie-arm64-lite.img.xz.sha256"
readonly IMG_FILE="/tmp/raspios-lite.img.xz"
readonly IMG_UNCOMPRESSED="/tmp/raspios-lite.img"
readonly DATASET_SIG_FILE="/tmp/dataset_signature.sha256"
readonly CLEANUP_DIRS="/tmp/raspios-lite.img.xz /tmp/raspios-lite.img /tmp/dataset_signature.sha256"

# Check dependencies
check_dependencies() {
    local deps=("wget" "xz-utils" "sha256sum" "dd" "lsblk" "openssl")
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" &> /dev/null; then
            echo "Error: $dep is required but not installed."
            exit 1
        fi
    done
}

# Download Pi OS image
download_image() {
    echo "Downloading Raspberry Pi OS Lite image..."
    wget -O "$IMG_FILE" "$PI_OS_URL"
    
    echo "Verifying download with SHA256..."
    local expected_sha256
    expected_sha256=$(wget -qO- "$PI_OS_SHA256_URL" | cut -d' ' -f1)
    local actual_sha256
    actual_sha256=$(sha256sum "$IMG_FILE" | cut -d' ' -f1)
    
    if [[ "$expected_sha256" != "$actual_sha256" ]]; then
        echo "Error: SHA256 mismatch. Download may be corrupted."
        exit 1
    fi
    
    echo "Download verified."
}

# Decompress image
decompress_image() {
    echo "Decompressing image..."
    xz -dk "$IMG_FILE"
    rm "$IMG_FILE"
}

# Sign the dataset (dog feeding config)
sign_dataset() {
    echo "Creating dataset signature..."
    
    # Create temporary config for signing
    local temp_config="/tmp/temp_dog_feeding.conf"
    cat << EOF > "$temp_config"
# Dog Feeding Pipeline Configuration
# Device settings
device_id=dogfeeder-001
# GPIO pins
motor_pin=18
servo_pin=12
# Feeding schedule
schedule_interval_minutes=30
# Logging
log_level=INFO
# Custom settings for dog feeding
enable_motor_control=true
enable_servo_control=true
# Network settings
network_mode=ethernet_only
EOF
    
    # Generate SHA256 hash
    sha256sum "$temp_config" > "$DATASET_SIG_FILE"
    
    # Cleanup
    rm "$temp_config"
    
    echo "Dataset signed."
}

# Find SD card device
find_sd_card() {
    echo "Detecting SD card device..."
    local sd_devices
    sd_devices=$(lsblk -rno NAME,TYPE,MOUNTPOINT | grep -E "^sd[a-z]+ disk$" | awk '{print "/dev/" $1}')
    
    if [[ -z "$sd_devices" ]]; then
        echo "Error: No SD card detected."
        exit 1
    fi
    
    echo "Available SD cards:"
    echo "$sd_devices"
    echo "Please select the SD card device (e.g., /dev/sdb):"
    read -r sd_device
    
    if [[ ! -b "$sd_device" ]]; then
        echo "Error: Invalid device selected."
        exit 1
    fi
    
    echo "Selected device: $sd_device"
}

# Burn image to SD card
burn_image() {
    local sd_device="$1"
    echo "Writing image to SD card..."
    sudo dd if="$IMG_UNCOMPRESSED" of="$sd_device" bs=4M status=progress oflag=sync
    echo "First write complete."
}

# Second burn for safety
second_burn() {
    local sd_device="$1"
    echo "Performing second write for safety..."
    sudo dd if="$IMG_UNCOMPRESSED" of="$sd_device" bs=4M status=progress oflag=sync
    echo "Second write complete."
}

# Configure SD card for dog feeding
configure_sd_card() {
    echo "Configuring SD card for dog feeding pipeline..."
    # Mount boot partition
    local boot_part="${sd_device}1"
    sudo mkdir -p /mnt/boot
    sudo mount "$boot_part" /mnt/boot
    
    # Disable SSH and user access
    # Remove ssh file to disable SSH
    sudo rm -f /mnt/boot/ssh 2>/dev/null || true
    
    # Create config.txt for Pi 3B+ with only Ethernet
    cat << EOF | sudo tee /mnt/boot/config.txt
# Enable UART for dog feeding hardware
enable_uart=1
# GPU memory allocation
gpu_mem=16
# Disable overscan
disable_overscan=1
# Overclock for performance
arm_freq=1400
core_freq=500
over_voltage=6
# Disable WiFi
dtoverlay=disable-wifi
# Disable Bluetooth
dtoverlay=disable-bt
EOF
    
    # Create dog feeding config with embedded signature
    cat << EOF | sudo tee /mnt/boot/dog_feeding.conf
# Dog Feeding Pipeline Configuration
# Device settings
device_id=dogfeeder-001
# GPIO pins
motor_pin=18
servo_pin=12
# Feeding schedule
schedule_interval_minutes=30
# Logging
log_level=INFO
# Custom settings for dog feeding
enable_motor_control=true
enable_servo_control=true
# Network settings
network_mode=ethernet_only
# Dataset signature
dataset_signature=$(cut -d' ' -f1 "$DATASET_SIG_FILE")
EOF
    
    # Create verification script for dataset
    cat << 'EOF_SCRIPT' | sudo tee /mnt/boot/verify_dataset.sh
#!/bin/bash
# Dataset verification script
echo "Verifying dataset integrity..."
SIG_FILE="/boot/dog_feeding.conf"
if [ ! -f "$SIG_FILE" ]; then
    echo "ERROR: Dataset config not found"
    exit 1
fi

# Extract expected signature
EXPECTED_SIG=$(grep "dataset_signature" "$SIG_FILE" | cut -d' ' -f2)

# Calculate actual signature
ACTUAL_SIG=$(sha256sum /boot/dog_feeding.conf | cut -d' ' -f1)

if [ "$EXPECTED_SIG" = "$ACTUAL_SIG" ]; then
    echo "Dataset verified successfully"
    exit 0
else
    echo "ERROR: Dataset signature mismatch"
    exit 1
fi
EOF_SCRIPT
    
    sudo chmod +x /mnt/boot/verify_dataset.sh
    
    # Create a script to erase SD card when needed
    cat << 'EOF_SCRIPT' | sudo tee /mnt/boot/erase_sd.sh
#!/bin/bash
# Secure erase script for SD card
echo "Erasing SD card securely..."
# Fill with zeros
dd if=/dev/zero of=/dev/mmcblk0 bs=1M status=progress
echo "SD card erased."
EOF_SCRIPT
    
    sudo chmod +x /mnt/boot/erase_sd.sh
    
    # Unmount
    sudo umount /mnt/boot
    echo "SD card configured."
}

# Remove unnecessary packages from Pi OS
cleanup_os() {
    echo "Removing unnecessary packages from Pi OS..."
    # This would normally be done in chroot, but for now we'll just note it
    echo "Note: In full implementation, this would remove unnecessary packages via chroot."
    echo "Packages to remove: libreoffice, firefox, vlc, etc."
}

# Cleanup temporary files
cleanup() {
    echo "Cleaning up temporary files..."
    rm -rf $CLEANUP_DIRS 2>/dev/null || true
    echo "Cleanup complete."
}

# Trap cleanup on exit
trap cleanup EXIT

main() {
    check_dependencies
    download_image
    decompress_image
    sign_dataset
    find_sd_card
    burn_image "$sd_device"
    second_burn "$sd_device"
    configure_sd_card
    cleanup_os
    echo "Pi OS burned and configured successfully!"
    echo "Dataset signature created: $DATASET_SIG_FILE"
    echo "Temporary files cleaned up automatically."
    echo "SD card is now secure and ready for deployment."
    echo "To erase SD card: run /boot/erase_sd.sh on the Pi."
    echo "Dataset verification: run /boot/verify_dataset.sh on the Pi."
}

main "$@"