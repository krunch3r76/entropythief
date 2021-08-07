// randwrite.c
// executable project that inputs a number of bytes and writes
// measures of 8 (64 bit random values) to kFilename
//
/* author: krunch3r (KJM github.com/krunch3r76) */
/* license: General Poetic License (GPL3) */

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/random.h>



char const * kFilename = "/golem/output/result.bin";



int from_devrand(uint64_t *buf_holding_random_bytes, uint64_t count)
{
	int STATUS=0;
	char getrandomBuf[256]; // getrandom guarantees up to 256 bytes per read
	ssize_t bytes_acquired;
	size_t next_len_requested;
	while(count !=0) {
			if(count >=256) {
				next_len_requested=256;
			} else {
				next_len_requested=count;
			}
			bytes_acquired = getrandom(getrandomBuf, next_len_requested, GRND_RANDOM);
			memcpy((void *)buf_holding_random_bytes, (void *)getrandomBuf, bytes_acquired);
			buf_holding_random_bytes+=bytes_acquired;

			count-=bytes_acquired;
	}
	return STATUS;
}










int rdrand_step (uint64_t *rand)
{
		unsigned char ok;
		asm volatile ("rdrand %0; setc %1"
						: "=r" (*rand), "=qm" (ok));
		return (int) ok;
}






int from_rdrand(uint64_t *buf_holding_random_bytes, uint64_t count)
{
	int STATUS = 0;
	uint64_t next_random_value;
	for (uint64_t i=0; i < count; ++i)
	{
		while (rdrand_step(&next_random_value) != 1) {};
		*buf_holding_random_bytes++=next_random_value;
	}
	return STATUS;
	
}





int main(int argc, char *argv[])
{
	int STATUS=0;
	// parse argument 1 for count
	char *end;
	FILE *fp_to_output_file;

	uint64_t count = strtoull(argv[1], &end, 10);
	if (*end != '\0') {
		STATUS = EXIT_FAILURE;
	}
	count /= 8; // discard any partial measurement of 8, ie remainder


	uint64_t *buf_holding_random_bytes = (uint64_t*)malloc(count*sizeof(*buf_holding_random_bytes));
	uint64_t *beg = buf_holding_random_bytes;

	// determine entropy source
	if (strncmp(argv[2], "rdrand", 6) == 0) {
		STATUS = from_rdrand(buf_holding_random_bytes, count);
		if (STATUS) fprintf(stderr, "Error calling routine to read from cpu.");
	} else if (strncmp(argv[2], "devrand", 7) == 0) {
		STATUS = from_devrand(buf_holding_random_bytes, count);
		if (STATUS) fprintf(stderr, "Error calling routine to read from kernel.");
	}

	if (STATUS == 0) {
		if ((fp_to_output_file = fopen(kFilename, "w+") ) == NULL) {
			STATUS=EXIT_FAILURE;
			fprintf(stderr, "Error opening %s for writing.", kFilename);
		}
	}

	if (STATUS == 0) {
			if (!fwrite(beg, sizeof(uint64_t), count, fp_to_output_file)) {
				STATUS=EXIT_FAILURE;
				fprintf(stderr, "Error writing to %s.", kFilename);
			}
			fclose(fp_to_output_file);
	}


	return STATUS;
}