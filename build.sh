#!/bin/sh
/usr/bin/cc -I/usr/include/python3.8 -fPIC -O0 -std=gnu11 -o rdrand.c.o -c rdrand.c
/usr/bin/cc -shared -Wl,-soname,librdrand.so -o rdrand.so rdrand.c.o -lpython3.8

