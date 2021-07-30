#!/bin/sh
# build.sh
# author: krunch3r (KJM github.com/krunch3r76)
# license: General Poetic License (GPL3)

/usr/bin/cc -I/usr/local/include/python3.9 -fPIC -O0 -std=gnu11 -o rdrand.c.o -c rdrand.c
/usr/bin/cc -shared -Wl,-soname,librdrand.so -o rdrand.so rdrand.c.o -lpython3.9

