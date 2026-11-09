#ifndef NODE_SIGNATURE_H
#define NODE_SIGNATURE_H

#include <stdbool.h>
#include <stddef.h>
#include <string.h>

/* Fixed work for equal-length SHA256 hex MACs, including uppercase input. */
static inline bool node_signature_matches(const char *provided, const char *expected) {
    if (provided == NULL || expected == NULL ||
        strlen(provided) != 64 || strlen(expected) != 64) {
        return false;
    }
    volatile unsigned char mismatch = 0;
    for (size_t i = 0; i < 64; i++) {
        unsigned char a = (unsigned char)provided[i];
        unsigned char b = (unsigned char)expected[i];
        a = (a >= 'A' && a <= 'F') ? (unsigned char)(a - 'A' + 'a') : a;
        b = (b >= 'A' && b <= 'F') ? (unsigned char)(b - 'A' + 'a') : b;
        mismatch |= (unsigned char)(a ^ b);
    }
    return mismatch == 0;
}

#endif
