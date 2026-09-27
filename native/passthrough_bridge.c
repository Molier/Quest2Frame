// SPDX-License-Identifier: GPL-3.0-only
// Experimental full-background FB passthrough -> native alpha blend bridge.
// Installed only by the separate experimental build tool, never by default.
#define _GNU_SOURCE
#define XR_EXTENSION_PROTOTYPES
#include <openxr/openxr.h>
#include <dlfcn.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef __ANDROID__
#include <android/log.h>
#define LOG(...) __android_log_print(ANDROID_LOG_INFO, "Q2FPassthrough", __VA_ARGS__)
#else
#define LOG(...) fprintf(stderr, __VA_ARGS__)
#endif

static pthread_once_t once = PTHREAD_ONCE_INIT;
static void *library;
static PFN_xrGetInstanceProcAddr original;
static pthread_mutex_t mutex = PTHREAD_MUTEX_INITIALIZER;
typedef struct {
    uintptr_t handle, parent;
    XrSession session;
    int running, kind;
    float opacity;
} Object;
static Object objects[32];
static uintptr_t sequence = 0x51324600;
typedef struct { XrSession handle; int alpha; } Session;
static Session sessions[8];

static void initialize(void) {
    Dl_info self;
    char path[4096];
    if (!dladdr((void *)&initialize, &self)) return;
    if (snprintf(path, sizeof(path), "%s", self.dli_fname) >= (int)sizeof(path)) return;
    char *slash = strrchr(path, '/');
    if (!slash) return;
    snprintf(slash+1, sizeof(path)-(size_t)(slash+1-path), "libq2f_original.so");
    library = dlopen(path, RTLD_NOW | RTLD_LOCAL);
    if (library) original = (PFN_xrGetInstanceProcAddr)dlsym(library, "xrGetInstanceProcAddr");
    LOG("experimental alpha bridge loaded; original=%s", original ? "OK" : "FAILED");
}
static PFN_xrVoidFunction resolve(const char *name) {
    pthread_once(&once, initialize);
    return library ? (PFN_xrVoidFunction)dlsym(library, name) : NULL;
}
static Object *find(uintptr_t handle, int kind) {
    for (size_t i=0;i<32;++i)
        if (objects[i].handle==handle && objects[i].kind==kind) return &objects[i];
    return NULL;
}
static Object *allocate(int kind, XrSession session, uintptr_t parent, int running) {
    for (size_t i=0;i<32;++i) if (!objects[i].handle) {
        objects[i]=(Object){++sequence,parent,session,running,kind,1.f};
        return &objects[i];
    }
    return NULL;
}
static int alpha_supported(XrSession session) {
    for (size_t i=0;i<8;++i) if (sessions[i].handle==session) return sessions[i].alpha;
    return 0;
}

XRAPI_ATTR XrResult XRAPI_CALL xrCreateSession(XrInstance instance, const XrSessionCreateInfo *info, XrSession *out) {
    PFN_xrCreateSession fn=(PFN_xrCreateSession)resolve("xrCreateSession");
    PFN_xrEnumerateEnvironmentBlendModes modes=(PFN_xrEnumerateEnvironmentBlendModes)resolve("xrEnumerateEnvironmentBlendModes");
    if (!fn || !info || !out) return XR_ERROR_INITIALIZATION_FAILED;
    int alpha=0;
    uint32_t n=0;
    if (modes && XR_SUCCEEDED(modes(instance,info->systemId,XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO,0,&n,NULL)) && n<=32) {
        XrEnvironmentBlendMode values[32];
        if (XR_SUCCEEDED(modes(instance,info->systemId,XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO,32,&n,values)))
            for(uint32_t i=0;i<n;++i) if(values[i]==XR_ENVIRONMENT_BLEND_MODE_ALPHA_BLEND) alpha=1;
    }
    XrResult r=fn(instance,info,out);
    if (XR_SUCCEEDED(r)) {
        pthread_mutex_lock(&mutex);
        for(size_t i=0;i<8;++i) if(!sessions[i].handle) {sessions[i]=(Session){*out,alpha};break;}
        pthread_mutex_unlock(&mutex);
        LOG("session created, alpha blend supported=%d",alpha);
    }
    return r;
}
XRAPI_ATTR XrResult XRAPI_CALL xrDestroySession(XrSession session) {
    PFN_xrDestroySession fn=(PFN_xrDestroySession)resolve("xrDestroySession");
    if (!fn) return XR_ERROR_FUNCTION_UNSUPPORTED;
    XrResult r=fn(session);
    if (XR_SUCCEEDED(r)) {
        pthread_mutex_lock(&mutex);
        for(size_t i=0;i<32;++i) if(objects[i].session==session) objects[i]=(Object){0};
        for(size_t i=0;i<8;++i) if(sessions[i].handle==session) sessions[i]=(Session){0};
        pthread_mutex_unlock(&mutex);
    }
    return r;
}
XRAPI_ATTR XrResult XRAPI_CALL xrCreatePassthroughFB(XrSession session, const XrPassthroughCreateInfoFB *info, XrPassthroughFB *out) {
    if(!info || !out || info->type!=XR_TYPE_PASSTHROUGH_CREATE_INFO_FB) return XR_ERROR_VALIDATION_FAILURE;
    *out=XR_NULL_HANDLE;
    pthread_mutex_lock(&mutex);
    if(!alpha_supported(session)) {pthread_mutex_unlock(&mutex);return XR_ERROR_FEATURE_UNSUPPORTED;}
    Object *p=allocate(1,session,0,!!(info->flags & XR_PASSTHROUGH_IS_RUNNING_AT_CREATION_BIT_FB));
    if(p) *out=(XrPassthroughFB)p->handle;
    pthread_mutex_unlock(&mutex);
    LOG("create passthrough result=%s session=%p handle=%p",p ? "OK" : "LIMIT",(void *)session,(void *)*out);
    return p ? XR_SUCCESS : XR_ERROR_LIMIT_REACHED;
}
static XrResult running(uintptr_t handle,int kind,int value) {
    pthread_mutex_lock(&mutex);
    Object *p=find(handle,kind);
    if(p) p->running=value;
    pthread_mutex_unlock(&mutex);
    return p ? XR_SUCCESS : XR_ERROR_HANDLE_INVALID;
}
static XrResult destroy(uintptr_t handle,int kind) {
    pthread_mutex_lock(&mutex);
    Object *p=find(handle,kind);
    if(p) {
        for(size_t i=0;i<32;++i) if(objects[i].parent==handle) objects[i]=(Object){0};
        *p=(Object){0};
    }
    pthread_mutex_unlock(&mutex);
    return p ? XR_SUCCESS : XR_ERROR_HANDLE_INVALID;
}
XRAPI_ATTR XrResult XRAPI_CALL xrDestroyPassthroughFB(XrPassthroughFB p) {return destroy((uintptr_t)p,1);}
XRAPI_ATTR XrResult XRAPI_CALL xrPassthroughStartFB(XrPassthroughFB p) {return running((uintptr_t)p,1,1);}
XRAPI_ATTR XrResult XRAPI_CALL xrPassthroughPauseFB(XrPassthroughFB p) {return running((uintptr_t)p,1,0);}
XRAPI_ATTR XrResult XRAPI_CALL xrDestroyPassthroughLayerFB(XrPassthroughLayerFB p) {return destroy((uintptr_t)p,2);}
XRAPI_ATTR XrResult XRAPI_CALL xrPassthroughLayerResumeFB(XrPassthroughLayerFB p) {return running((uintptr_t)p,2,1);}
XRAPI_ATTR XrResult XRAPI_CALL xrPassthroughLayerPauseFB(XrPassthroughLayerFB p) {return running((uintptr_t)p,2,0);}
XRAPI_ATTR XrResult XRAPI_CALL xrCreatePassthroughLayerFB(XrSession session,const XrPassthroughLayerCreateInfoFB *info,XrPassthroughLayerFB *out) {
    if(!info || !out || info->type!=XR_TYPE_PASSTHROUGH_LAYER_CREATE_INFO_FB) return XR_ERROR_VALIDATION_FAILURE;
    *out=XR_NULL_HANDLE;
    if(info->purpose!=XR_PASSTHROUGH_LAYER_PURPOSE_RECONSTRUCTION_FB) return XR_ERROR_FEATURE_UNSUPPORTED;
    pthread_mutex_lock(&mutex);
    Object *parent=find((uintptr_t)info->passthrough,1);
    // This OVRPlugin build submits a null parent despite successfully creating
    // a passthrough object. Resolve it only when ownership is unambiguous.
    if(!info->passthrough) {
        for(size_t i=0;i<32;++i) if(objects[i].kind==1 && objects[i].session==session) {
            if(parent) {parent=NULL;break;}
            parent=&objects[i];
        }
    }
    if(!parent || parent->session!=session) {
        static unsigned failures;
        if(failures++<4) LOG("layer invalid parent=%p found=%d session=%p expected=%p",(void *)info->passthrough,parent!=NULL,(void *)session,parent ? (void *)parent->session : NULL);
        pthread_mutex_unlock(&mutex);return XR_ERROR_HANDLE_INVALID;
    }
    Object *p=allocate(2,session,parent->handle,!!(info->flags & XR_PASSTHROUGH_IS_RUNNING_AT_CREATION_BIT_FB));
    if(p) *out=(XrPassthroughLayerFB)p->handle;
    LOG("create layer purpose=%d session=%p parent=%p resolved=%p layer=%p flags=%llu",info->purpose,(void *)session,(void *)info->passthrough,(void *)parent->handle,(void *)*out,(unsigned long long)info->flags);
    pthread_mutex_unlock(&mutex);
    return p ? XR_SUCCESS : XR_ERROR_LIMIT_REACHED;
}
XRAPI_ATTR XrResult XRAPI_CALL xrPassthroughLayerSetStyleFB(XrPassthroughLayerFB handle,const XrPassthroughStyleFB *style) {
    if(!style || style->type!=XR_TYPE_PASSTHROUGH_STYLE_FB || !(style->textureOpacityFactor>=0 && style->textureOpacityFactor<=1)) return XR_ERROR_VALIDATION_FAILURE;
    // Native background blending cannot represent per-camera color, edges, or fractional opacity.
    if(style->next || style->edgeColor.a!=0 || (style->textureOpacityFactor!=0 && style->textureOpacityFactor!=1)) return XR_ERROR_FEATURE_UNSUPPORTED;
    pthread_mutex_lock(&mutex);
    Object *p=find((uintptr_t)handle,2);
    if(p) p->opacity=style->textureOpacityFactor;
    pthread_mutex_unlock(&mutex);
    return p ? XR_SUCCESS : XR_ERROR_HANDLE_INVALID;
}
// OVRPlugin looks these up during initialization, even for reconstruction-only use.
// Supply real failure results when invoked; never manufacture mesh/camera handles.
XRAPI_ATTR XrResult XRAPI_CALL xrCreateTriangleMeshFB(XrSession s,const XrTriangleMeshCreateInfoFB *i,XrTriangleMeshFB *o) {
    (void)s;(void)i;if(o)*o=XR_NULL_HANDLE;return XR_ERROR_FEATURE_UNSUPPORTED;
}
XRAPI_ATTR XrResult XRAPI_CALL xrDestroyTriangleMeshFB(XrTriangleMeshFB m) {(void)m;return XR_ERROR_HANDLE_INVALID;}
XRAPI_ATTR XrResult XRAPI_CALL xrCreateGeometryInstanceFB(XrSession s,const XrGeometryInstanceCreateInfoFB *i,XrGeometryInstanceFB *o) {
    (void)s;(void)i;if(o)*o=XR_NULL_HANDLE;return XR_ERROR_FEATURE_UNSUPPORTED;
}
XRAPI_ATTR XrResult XRAPI_CALL xrDestroyGeometryInstanceFB(XrGeometryInstanceFB i) {(void)i;return XR_ERROR_HANDLE_INVALID;}
XRAPI_ATTR XrResult XRAPI_CALL xrGeometryInstanceSetTransformFB(XrGeometryInstanceFB i,const XrGeometryInstanceTransformFB *t) {(void)i;(void)t;return XR_ERROR_HANDLE_INVALID;}
XRAPI_ATTR XrResult XRAPI_CALL xrPassthroughLayerSetKeyboardHandsIntensityFB(XrPassthroughLayerFB l,const XrPassthroughKeyboardHandsIntensityFB *i) {(void)l;(void)i;return XR_ERROR_FEATURE_UNSUPPORTED;}

XRAPI_ATTR XrResult XRAPI_CALL xrEndFrame(XrSession session,const XrFrameEndInfo *info) {
    PFN_xrEndFrame fn=(PFN_xrEndFrame)resolve("xrEndFrame");
    if(!fn || !info) return XR_ERROR_INITIALIZATION_FAILED;
    if(info->layerCount>64 || (info->layerCount && !info->layers)) return XR_ERROR_VALIDATION_FAILURE;
    const XrCompositionLayerBaseHeader *layers[64];
    uint32_t count=0;int active=0,seen=0;
    pthread_mutex_lock(&mutex);
    for(uint32_t i=0;i<info->layerCount;++i) {
        const XrCompositionLayerBaseHeader *layer=info->layers[i];
        if(!layer) {pthread_mutex_unlock(&mutex);return XR_ERROR_LAYER_INVALID;}
        if(layer->type!=XR_TYPE_COMPOSITION_LAYER_PASSTHROUGH_FB) {layers[count++]=layer;continue;}
        seen=1;
        const XrCompositionLayerPassthroughFB *pt=(const void *)layer;
        Object *p=find((uintptr_t)pt->layerHandle,2);
        Object *parent=p ? find(p->parent,1) : NULL;
        if(!p || !parent || p->session!=session) {pthread_mutex_unlock(&mutex);return XR_ERROR_HANDLE_INVALID;}
        if(p->running && parent->running && p->opacity>0) {
            // Only an underlay can be represented by the environment background.
            if(count) {pthread_mutex_unlock(&mutex);return XR_ERROR_FEATURE_UNSUPPORTED;}
            active=1;
        }
    }
    pthread_mutex_unlock(&mutex);
    if(!seen) return fn(session,info);
    XrFrameEndInfo fixed=*info;
    fixed.layerCount=count;fixed.layers=layers;
    if(active) fixed.environmentBlendMode=XR_ENVIRONMENT_BLEND_MODE_ALPHA_BLEND;
    XrResult r=fn(session,&fixed);
    static int last=-999;
    int state=XR_FAILED(r) ? r : active;
    pthread_mutex_lock(&mutex);
    if(last!=state) {LOG("passthrough frame active=%d layers=%u blend=%d result=%d flags=%llu",active,count,fixed.environmentBlendMode,r,(unsigned long long)(count ? layers[0]->layerFlags : 0));last=state;}
    pthread_mutex_unlock(&mutex);
    return r;
}
XRAPI_ATTR XrResult XRAPI_CALL xrGetInstanceProcAddr(XrInstance instance,const char *name,PFN_xrVoidFunction *out) {
    pthread_once(&once,initialize);
    if(!name || !out) return XR_ERROR_VALIDATION_FAILURE;
    *out=NULL;
    if(!original) return XR_ERROR_INITIALIZATION_FAILED;
#define HOOK(n) if(!strcmp(name,#n)) {*out=(PFN_xrVoidFunction)n;return XR_SUCCESS;}
    HOOK(xrGetInstanceProcAddr) HOOK(xrCreateSession) HOOK(xrDestroySession) HOOK(xrEndFrame)
    HOOK(xrCreatePassthroughFB) HOOK(xrDestroyPassthroughFB) HOOK(xrPassthroughStartFB) HOOK(xrPassthroughPauseFB)
    HOOK(xrCreatePassthroughLayerFB) HOOK(xrDestroyPassthroughLayerFB)
    HOOK(xrPassthroughLayerResumeFB) HOOK(xrPassthroughLayerPauseFB) HOOK(xrPassthroughLayerSetStyleFB)
    HOOK(xrCreateTriangleMeshFB) HOOK(xrDestroyTriangleMeshFB)
    HOOK(xrCreateGeometryInstanceFB) HOOK(xrDestroyGeometryInstanceFB) HOOK(xrGeometryInstanceSetTransformFB)
    HOOK(xrPassthroughLayerSetKeyboardHandsIntensityFB)
#undef HOOK
    return original(instance,name,out);
}
