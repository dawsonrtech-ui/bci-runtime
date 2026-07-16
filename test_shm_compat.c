#include <fcntl.h>
#include <sys/mman.h>
#include <stdio.h>
#include <unistd.h>
#include <string.h>
#include <errno.h>

int main() {
    // Create file with regular open (like Python does)
    int fd1 = open("/dev/shm/test_shm_compat", O_CREAT | O_RDWR, 0666);
    if (fd1 < 0) { perror("open create"); return 1; }
    ftruncate(fd1, 1024);
    close(fd1);
    printf("Created with open(): /dev/shm/test_shm_compat\n");

    // Try to open with shm_open (like Unity does)
    int fd2 = shm_open("/test_shm_compat", O_RDWR, 0);
    if (fd2 < 0) {
        printf("shm_open FAILED: %s\n", strerror(errno));
        // Now try with O_CREAT
        int fd3 = shm_open("/test_shm_compat", O_RDWR | O_CREAT, 0666);
        if (fd3 < 0) {
            printf("shm_open with O_CREAT also FAILED: %s\n", strerror(errno));
            return 1;
        }
        printf("shm_open with O_CREAT OK, fd=%d\n", fd3);
        close(fd3);
    } else {
        printf("shm_open OK, fd=%d\n", fd2);
        close(fd2);
    }

    // Cleanup
    shm_unlink("/test_shm_compat");
    unlink("/dev/shm/test_shm_compat");
    printf("Done\n");
    return 0;
}
