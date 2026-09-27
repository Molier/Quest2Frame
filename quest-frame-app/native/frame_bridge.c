// SPDX-License-Identifier: GPL-3.0-only
#define _GNU_SOURCE
#define XR_EXTENSION_PROTOTYPES
#include <openxr/openxr.h>
#include <android/log.h>
#include <dlfcn.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void *library;
static PFN_xrGetInstanceProcAddr original;
static pthread_once_t once = PTHREAD_ONCE_INIT;
static XrInstance current;
static float scale = 1.0f;
static int foveation_fix = 1, controller_fix = 1;

static void settings(const char *path) {
    FILE *f = fopen(path, "r");
    if (!f) return;
    char line[256]; float value;
    while (fgets(line, sizeof(line), f)) {
        if (sscanf(line, "scale=%f", &value) == 1 && value >= .5f && value <= 2.f) scale = value;
        if (sscanf(line, "foveation_fix=%f", &value) == 1) foveation_fix = value != 0;
        if (sscanf(line, "controller_fix=%f", &value) == 1) controller_fix = value != 0;
    }
    fclose(f);
}
static void initialize(void) {
    Dl_info self; char path[4096], process[256] = {0};
    if (!dladdr((void *)&initialize, &self)) return;
    snprintf(path, sizeof(path), "%s", self.dli_fname);
    char *slash = strrchr(path, '/'); if (!slash) return;
    size_t remaining = sizeof(path) - (size_t)(slash + 1 - path);
    snprintf(slash + 1, remaining, "libframe_settings.so"); settings(path);
    snprintf(slash + 1, remaining, "libopenxr_loader_original.so");
    library = dlopen(path, RTLD_NOW | RTLD_LOCAL);
    if (library) original = (PFN_xrGetInstanceProcAddr)dlsym(library, "xrGetInstanceProcAddr");
    FILE *f = fopen("/proc/self/cmdline", "r");
    if (f) { fread(process, 1, sizeof(process)-1, f); fclose(f); }
    char *colon = strchr(process, ':'); if (colon) *colon = 0;
    if (*process && !strchr(process, '/')) {
        snprintf(path, sizeof(path), "/sdcard/Android/data/%s/files/framebridge.conf", process);
        settings(path);
    }
    const char *config = getenv("FRAMEBRIDGE_CONFIG");
    if (config && *config) settings(config);
    __android_log_print(ANDROID_LOG_INFO, "FrameBridge", "scale=%.2f foveation_fix=%d controller_fix=%d loader=%s", scale, foveation_fix, controller_fix, original ? "OK" : "FAILED");
}
static PFN_xrVoidFunction resolve(XrInstance instance, const char *name) {
    pthread_once(&once, initialize);
    PFN_xrVoidFunction fn = NULL;
    if (original) original(instance, name, &fn);
    if (!fn && library) fn = (PFN_xrVoidFunction)dlsym(library, name);
    return fn;
}
XRAPI_ATTR XrResult XRAPI_CALL xrCreateInstance(const XrInstanceCreateInfo *info, XrInstance *instance) {
    PFN_xrCreateInstance fn = (PFN_xrCreateInstance)resolve(XR_NULL_HANDLE, "xrCreateInstance");
    if (!fn || !info) return XR_ERROR_INITIALIZATION_FAILED;
    int has = 0, enabled = 0;
    for (const XrBaseInStructure *p = info->next; p; p = p->next)
        if (p->type == XR_TYPE_INSTANCE_CREATE_INFO_ANDROID_KHR) has = 1;
    for (uint32_t i=0; i<info->enabledExtensionCount; ++i)
        if (!strcmp(info->enabledExtensionNames[i], "XR_KHR_android_create_instance")) enabled = 1;
    XrInstanceCreateInfo fixed = *info;
    const char **names = NULL;
    if (has && !enabled) {
        names = calloc(info->enabledExtensionCount + 1, sizeof(*names));
        if (!names) return XR_ERROR_OUT_OF_MEMORY;
        for (uint32_t i=0; i<info->enabledExtensionCount; ++i) names[i] = info->enabledExtensionNames[i];
        names[info->enabledExtensionCount] = "XR_KHR_android_create_instance";
        fixed.enabledExtensionNames = names; fixed.enabledExtensionCount++;
    }
    XrResult result = fn(&fixed, instance); free(names);
    if (XR_SUCCEEDED(result)) current = *instance;
    return result;
}
XRAPI_ATTR XrResult XRAPI_CALL xrEnumerateViewConfigurationViews(XrInstance instance, XrSystemId system, XrViewConfigurationType type, uint32_t capacity, uint32_t *count, XrViewConfigurationView *views) {
    PFN_xrEnumerateViewConfigurationViews fn = (PFN_xrEnumerateViewConfigurationViews)resolve(instance, "xrEnumerateViewConfigurationViews");
    if (!fn) return XR_ERROR_FUNCTION_UNSUPPORTED;
    XrResult result = fn(instance, system, type, capacity, count, views);
    if (XR_SUCCEEDED(result) && views && count) for (uint32_t i=0; i<*count && i<capacity; ++i) {
        uint32_t w = (uint32_t)(views[i].recommendedImageRectWidth * scale + .5f);
        uint32_t h = (uint32_t)(views[i].recommendedImageRectHeight * scale + .5f);
        views[i].recommendedImageRectWidth = w > views[i].maxImageRectWidth ? views[i].maxImageRectWidth : (w ? w : 1);
        views[i].recommendedImageRectHeight = h > views[i].maxImageRectHeight ? views[i].maxImageRectHeight : (h ? h : 1);
        __android_log_print(ANDROID_LOG_INFO, "FrameBridge", "view=%u recommended=%ux%u scale=%.2f", i, views[i].recommendedImageRectWidth, views[i].recommendedImageRectHeight, scale);
    }
    return result;
}
XRAPI_ATTR XrResult XRAPI_CALL xrCreateSwapchain(XrSession session, const XrSwapchainCreateInfo *info, XrSwapchain *swapchain) {
    PFN_xrCreateSwapchain fn = (PFN_xrCreateSwapchain)resolve(current, "xrCreateSwapchain");
    if (!fn || !info) return XR_ERROR_INITIALIZATION_FAILED;
    XrSwapchainCreateInfo fixed = *info;
    const XrBaseInStructure *next = fixed.next;
    while (foveation_fix && next && next->type == XR_TYPE_SWAPCHAIN_CREATE_INFO_FOVEATION_FB) next = next->next;
    fixed.next = next;
    XrResult result = fn(session, &fixed, swapchain);
    __android_log_print(ANDROID_LOG_INFO, "FrameBridge", "swapchain=%ux%u result=%d", fixed.width, fixed.height, result);
    return result;
}
XRAPI_ATTR XrResult XRAPI_CALL xrLocateHandJointsEXT(XrHandTrackerEXT tracker, const XrHandJointsLocateInfoEXT *info, XrHandJointLocationsEXT *locations) {
    if (!controller_fix) {
        PFN_xrLocateHandJointsEXT fn = (PFN_xrLocateHandJointsEXT)resolve(current, "xrLocateHandJointsEXT");
        return fn ? fn(tracker, info, locations) : XR_ERROR_FUNCTION_UNSUPPORTED;
    }
    if (!locations) return XR_ERROR_VALIDATION_FAILURE;
    locations->isActive = XR_FALSE;
    for (XrBaseOutStructure *p=locations->next; p; p=p->next)
        if (p->type == XR_TYPE_HAND_TRACKING_AIM_STATE_FB) ((XrHandTrackingAimStateFB *)p)->status = 0;
    return XR_SUCCESS;
}
XRAPI_ATTR XrResult XRAPI_CALL xrGetCurrentInteractionProfile(XrSession session, XrPath user, XrInteractionProfileState *state) {
    PFN_xrGetCurrentInteractionProfile fn = (PFN_xrGetCurrentInteractionProfile)resolve(current, "xrGetCurrentInteractionProfile");
    if (!fn) return XR_ERROR_FUNCTION_UNSUPPORTED;
    XrResult result = fn(session, user, state);
    if (controller_fix && XR_SUCCEEDED(result) && state->interactionProfile && current) {
        PFN_xrPathToString str = (PFN_xrPathToString)resolve(current, "xrPathToString");
        PFN_xrStringToPath path = (PFN_xrStringToPath)resolve(current, "xrStringToPath");
        char name[XR_MAX_PATH_LENGTH]; uint32_t size;
        if (str && path && XR_SUCCEEDED(str(current, state->interactionProfile, sizeof(name), &size, name)) && (strstr(name, "/valve/") || strstr(name, "/khr/generic_controller")))
            path(current, "/interaction_profiles/oculus/touch_controller", &state->interactionProfile);
    }
    return result;
}
XRAPI_ATTR XrResult XRAPI_CALL xrEnumerateInstanceExtensionProperties(const char *layer, uint32_t capacity, uint32_t *count, XrExtensionProperties *properties) {
    PFN_xrEnumerateInstanceExtensionProperties fn = (PFN_xrEnumerateInstanceExtensionProperties)resolve(XR_NULL_HANDLE, "xrEnumerateInstanceExtensionProperties");
    if (!fn || !count) return XR_ERROR_INITIALIZATION_FAILED;
    if (!foveation_fix) return fn(layer, capacity, count, properties);
    uint32_t total=0; XrResult result = fn(layer, 0, &total, NULL);
    if (XR_FAILED(result)) return result;
    XrExtensionProperties *all = calloc(total ? total : 1, sizeof(*all));
    if (!all) return XR_ERROR_OUT_OF_MEMORY;
    for (uint32_t i=0; i<total; ++i) all[i].type = XR_TYPE_EXTENSION_PROPERTIES;
    result = fn(layer, total, &total, all);
    if (XR_FAILED(result)) { free(all); return result; }
    uint32_t kept=0;
    for (uint32_t i=0; i<total; ++i) {
        if (strstr(all[i].extensionName, "foveation")) continue;
        if (properties && kept < capacity) properties[kept] = all[i];
        ++kept;
    }
    free(all); *count=kept;
    return capacity && capacity < kept ? XR_ERROR_SIZE_INSUFFICIENT : XR_SUCCESS;
}
XRAPI_ATTR XrResult XRAPI_CALL xrEnumerateApiLayerProperties(uint32_t capacity, uint32_t *count, XrApiLayerProperties *properties) {
    PFN_xrEnumerateApiLayerProperties fn = (PFN_xrEnumerateApiLayerProperties)resolve(XR_NULL_HANDLE, "xrEnumerateApiLayerProperties");
    return fn ? fn(capacity, count, properties) : XR_ERROR_INITIALIZATION_FAILED;
}
XRAPI_ATTR XrResult XRAPI_CALL xrGetInstanceProcAddr(XrInstance instance, const char *name, PFN_xrVoidFunction *function) {
    pthread_once(&once, initialize);
    if (!original) return XR_ERROR_INITIALIZATION_FAILED;
    if (!name || !function) return XR_ERROR_VALIDATION_FAILURE;
#define HOOK(n) if (!strcmp(name, #n)) { *function=(PFN_xrVoidFunction)n; return XR_SUCCESS; }
    HOOK(xrCreateInstance) HOOK(xrEnumerateViewConfigurationViews)
    HOOK(xrCreateSwapchain) HOOK(xrLocateHandJointsEXT)
    HOOK(xrGetCurrentInteractionProfile) HOOK(xrEnumerateInstanceExtensionProperties)
    return original(instance, name, function);
}
