/* randwrite.c  –  RDSEED-only tiny build
 * author: krunch3r (KJM github.com/krunch3r76)
 * license: GPL-3
 *
 * Usage:  randwrite <byte-count>
 *         (writes byte-count bytes of RDSEED output to kFilename)
 */

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>

static const char *kFilename = "/golem/output/result.bin";

/* ---------- RDSEED primitive --------------------------------- */
static inline int rdseed_step(uint64_t *x)
{
    unsigned char ok;
    asm volatile ("rdseed %0; setc %1"
                  : "=r" (*x), "=qm" (ok));
    return (int)ok;          /* 1 = success, 0 = retry */
}

/* ---------- bulk extractor ----------------------------------- */
static int from_rdseed(char *buf, uint64_t n)
{
    uint64_t full = n / 8, rem = n % 8, v;
    union { uint64_t d; unsigned char b[8]; } u;

    for (uint64_t i = 0; i < full; ++i) {
        while (!rdseed_step(&v)) ;      /* busy-wait until CF = 1 */
        *(uint64_t*)buf = v;
        buf += 8;
    }
    if (rem) {
        while (!rdseed_step(&v)) ;
        u.d = v;
        for (int i = rem - 1; i >= 0; --i)   /* little-endian tail */
            *buf++ = u.b[i];
    }
    return 0;
}

/* ---------- main --------------------------------------------- */
int main(int argc, char *argv[])
{
    if (argc < 2) {
        fprintf(stderr, "usage: %s <byte-count>\n", argv[0]);
        return EXIT_FAILURE;
    }

    char *end;
    uint64_t nbytes = strtoull(argv[1], &end, 10);
    if (*end) { fprintf(stderr, "invalid byte count\n"); return EXIT_FAILURE; }

    char *buf = calloc(nbytes, 1);
    if (!buf) { perror("calloc"); return EXIT_FAILURE; }

    if (from_rdseed(buf, nbytes)) { free(buf); return EXIT_FAILURE; }

    FILE *fp = fopen(kFilename, "wb");
    if (!fp || fwrite(buf, 1, nbytes, fp) != nbytes) {
        perror(kFilename);  if (fp) fclose(fp);  free(buf);  return EXIT_FAILURE;
    }
    fclose(fp);
    free(buf);
    return EXIT_SUCCESS;
}
