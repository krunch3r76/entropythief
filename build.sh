#!/bin/sh
# https://stackoverflow.com/questions/59895/how-can-i-get-the-source-directory-of-a-bash-script-from-within-the-script-itsel
# Dave Dopson
# SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

/usr/bin/cc -I/usr/local/include/python3.9 -fPIC -O0 -std=gnu11 -o rdrand.c.o -c rdrand.c
/usr/bin/cc -shared -Wl,-soname,librdrand.so -o rdrand.so rdrand.c.o -lpython3.9

