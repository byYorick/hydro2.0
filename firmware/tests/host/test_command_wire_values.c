#include <assert.h>
#include <math.h>
#include <stddef.h>
#include <string.h>

#include "node_pwm_command.h"
#include "node_signature.h"

int main(void) {
    node_pwm_value_t pwm;
    assert(node_pwm_decode(true, 73, false, 0, NODE_PWM_LEGACY_RAW, &pwm));
    assert(pwm.raw == 186 && fabsf(pwm.percent - 73.0f) < 0.001f);
    assert(node_pwm_decode(true, 0, true, 255, NODE_PWM_LEGACY_RAW, &pwm));
    assert(pwm.raw == 0 && pwm.percent == 0);
    assert(node_pwm_decode(true, 100, false, 0, NODE_PWM_LEGACY_RAW, &pwm));
    assert(pwm.raw == 255 && pwm.percent == 100);
    assert(!node_pwm_decode(true, -1, true, 255, NODE_PWM_LEGACY_RAW, &pwm));
    assert(!node_pwm_decode(true, 101, false, 0, NODE_PWM_LEGACY_RAW, &pwm));
    assert(!node_pwm_decode(true, NAN, true, 255, NODE_PWM_LEGACY_RAW, &pwm));
    assert(!node_pwm_decode(true, INFINITY, false, 0, NODE_PWM_LEGACY_RAW, &pwm));
    assert(!node_pwm_decode(false, 0, false, 0, NODE_PWM_LEGACY_RAW, &pwm));
    assert(!node_pwm_decode(false, 0, true, NAN, NODE_PWM_LEGACY_RAW, &pwm));
    assert(node_pwm_decode(false, 0, true, 73, NODE_PWM_LEGACY_RAW, &pwm));
    assert(pwm.raw == 73);
    assert(node_pwm_decode(false, 0, true, 73, NODE_PWM_LEGACY_PERCENT_OR_RAW, &pwm));
    assert(pwm.percent == 73 && pwm.raw == 186);
    assert(node_pwm_decode(false, 0, true, 128, NODE_PWM_LEGACY_PERCENT_OR_RAW, &pwm));
    assert(pwm.raw == 128 && fabsf(pwm.percent - 50.196f) < 0.001f);
    assert(node_pwm_decode(false, 0, true, 1e100, NODE_PWM_LEGACY_RAW, &pwm));
    assert(pwm.raw == 255);
    assert(node_pwm_decode(false, 0, true, -1, NODE_PWM_LEGACY_RAW, &pwm));
    assert(pwm.raw == 0);
    assert(!node_pwm_decode(false, 0, true, -1, NODE_PWM_LEGACY_PERCENT_OR_RAW, &pwm));

    const char *mac = "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789";
    const char *upper = "ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789";
    assert(node_signature_matches(mac, mac));
    assert(node_signature_matches(upper, mac));
    assert(!node_signature_matches(NULL, mac));
    assert(!node_signature_matches("short", mac));
    for (size_t i = 0; i < 64; ++i) {
        char bad[65];
        memcpy(bad, mac, sizeof(bad));
        bad[i] = 'z';
        assert(!node_signature_matches(bad, mac));
    }
    return 0;
}
