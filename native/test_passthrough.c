// SPDX-License-Identifier: GPL-3.0-only
// Host-side behavioral tests: gcc -I include test_passthrough.c -ldl -lpthread
#define _GNU_SOURCE
#define XR_EXTENSION_PROTOTYPES
#include <openxr/openxr.h>
#include <dlfcn.h>
#include <assert.h>
#include <string.h>
static void *mock_symbol(void *,const char *);
#define dlsym mock_symbol
#include "passthrough_bridge.c"
#undef dlsym

static XrEnvironmentBlendMode observed;
static uint32_t observed_count;
static XrResult frame_result=XR_SUCCESS;
static int offer_alpha=1;
static XrResult mock_end(XrSession s,const XrFrameEndInfo *info) {
    (void)s;observed=info->environmentBlendMode;observed_count=info->layerCount;
    for(uint32_t i=0;i<info->layerCount;++i) assert(info->layers[i]->type!=XR_TYPE_COMPOSITION_LAYER_PASSTHROUGH_FB);
    return frame_result;
}
static XrResult mock_create(XrInstance i,const XrSessionCreateInfo *c,XrSession *s) {(void)i;(void)c;*s=(XrSession)(uintptr_t)17;return XR_SUCCESS;}
static XrResult mock_destroy(XrSession s) {(void)s;return XR_SUCCESS;}
static XrResult mock_modes(XrInstance i,XrSystemId s,XrViewConfigurationType t,uint32_t cap,uint32_t *n,XrEnvironmentBlendMode *v) {
    (void)i;(void)s;(void)t;*n=offer_alpha?2:1;
    if(cap) {v[0]=XR_ENVIRONMENT_BLEND_MODE_OPAQUE;if(offer_alpha)v[1]=XR_ENVIRONMENT_BLEND_MODE_ALPHA_BLEND;}
    return XR_SUCCESS;
}
static void *mock_symbol(void *h,const char *n) {
    (void)h;
    if(!strcmp(n,"xrEndFrame"))return (void*)mock_end;
    if(!strcmp(n,"xrCreateSession"))return (void*)mock_create;
    if(!strcmp(n,"xrDestroySession"))return (void*)mock_destroy;
    if(!strcmp(n,"xrEnumerateEnvironmentBlendModes"))return (void*)mock_modes;
    return NULL;
}
static void ready(void) {library=(void*)1;}
int main(void) {
    pthread_once(&once,ready);
    XrSession s;
    XrSessionCreateInfo sc={.type=XR_TYPE_SESSION_CREATE_INFO};
    assert(xrCreateSession(XR_NULL_HANDLE,&sc,&s)==XR_SUCCESS);
    XrPassthroughCreateInfoFB pc={.type=XR_TYPE_PASSTHROUGH_CREATE_INFO_FB,.flags=1};
    XrPassthroughFB p;
    assert(xrCreatePassthroughFB(s,&pc,&p)==XR_SUCCESS);
    XrPassthroughLayerCreateInfoFB lc={.type=XR_TYPE_PASSTHROUGH_LAYER_CREATE_INFO_FB,.passthrough=p,.flags=1,.purpose=XR_PASSTHROUGH_LAYER_PURPOSE_PROJECTED_FB};
    XrPassthroughLayerFB l;
    assert(xrCreatePassthroughLayerFB(s,&lc,&l)==XR_ERROR_FEATURE_UNSUPPORTED);
    assert(l==XR_NULL_HANDLE);
    lc.purpose=XR_PASSTHROUGH_LAYER_PURPOSE_RECONSTRUCTION_FB;
    lc.passthrough=(XrPassthroughFB)(uintptr_t)99;
    assert(xrCreatePassthroughLayerFB(s,&lc,&l)==XR_ERROR_HANDLE_INVALID);
    lc.passthrough=XR_NULL_HANDLE;
    assert(xrCreatePassthroughLayerFB(s,&lc,&l)==XR_SUCCESS);
    XrPassthroughFB second;
    assert(xrCreatePassthroughFB(s,&pc,&second)==XR_SUCCESS);
    XrPassthroughLayerFB ambiguous;
    assert(xrCreatePassthroughLayerFB(s,&lc,&ambiguous)==XR_ERROR_HANDLE_INVALID);
    assert(xrDestroyPassthroughFB(second)==XR_SUCCESS);
    XrCompositionLayerPassthroughFB pt={.type=XR_TYPE_COMPOSITION_LAYER_PASSTHROUGH_FB,.layerHandle=l};
    XrCompositionLayerProjection projection={.type=XR_TYPE_COMPOSITION_LAYER_PROJECTION};
    const XrCompositionLayerBaseHeader *layers[]={(void*)&pt,(void*)&projection};
    XrFrameEndInfo frame={.type=XR_TYPE_FRAME_END_INFO,.environmentBlendMode=XR_ENVIRONMENT_BLEND_MODE_OPAQUE,.layerCount=2,.layers=layers};
    assert(xrEndFrame(s,&frame)==XR_SUCCESS);
    assert(observed==XR_ENVIRONMENT_BLEND_MODE_ALPHA_BLEND && observed_count==1);
    assert(frame.layerCount==2 && frame.environmentBlendMode==XR_ENVIRONMENT_BLEND_MODE_OPAQUE);
    assert(xrPassthroughPauseFB(p)==XR_SUCCESS);
    assert(xrEndFrame(s,&frame)==XR_SUCCESS && observed==XR_ENVIRONMENT_BLEND_MODE_OPAQUE);
    assert(xrPassthroughStartFB(p)==XR_SUCCESS);
    assert(xrPassthroughLayerPauseFB(l)==XR_SUCCESS);
    assert(xrEndFrame(s,&frame)==XR_SUCCESS && observed==XR_ENVIRONMENT_BLEND_MODE_OPAQUE);
    assert(xrPassthroughLayerResumeFB(l)==XR_SUCCESS);
    frame_result=XR_ERROR_RUNTIME_FAILURE;
    assert(xrEndFrame(s,&frame)==XR_ERROR_RUNTIME_FAILURE);
    frame_result=XR_SUCCESS;
    assert(xrEndFrame((XrSession)(uintptr_t)99,&frame)==XR_ERROR_HANDLE_INVALID);
    const XrCompositionLayerBaseHeader *reversed[]={(void*)&projection,(void*)&pt};
    frame.layers=reversed;
    assert(xrEndFrame(s,&frame)==XR_ERROR_FEATURE_UNSUPPORTED);
    frame.layers=layers;
    XrPassthroughStyleFB style={.type=XR_TYPE_PASSTHROUGH_STYLE_FB,.textureOpacityFactor=.5f};
    assert(xrPassthroughLayerSetStyleFB(l,&style)==XR_ERROR_FEATURE_UNSUPPORTED);
    style.textureOpacityFactor=0;
    assert(xrPassthroughLayerSetStyleFB(l,&style)==XR_SUCCESS);
    assert(xrEndFrame(s,&frame)==XR_SUCCESS && observed==XR_ENVIRONMENT_BLEND_MODE_OPAQUE);
    assert(xrDestroyPassthroughFB(p)==XR_SUCCESS);
    assert(xrPassthroughLayerResumeFB(l)==XR_ERROR_HANDLE_INVALID);
    assert(xrDestroyPassthroughFB(p)==XR_ERROR_HANDLE_INVALID);
    assert(xrDestroySession(s)==XR_SUCCESS);
    offer_alpha=0;
    assert(xrCreateSession(XR_NULL_HANDLE,&sc,&s)==XR_SUCCESS);
    assert(xrCreatePassthroughFB(s,&pc,&p)==XR_ERROR_FEATURE_UNSUPPORTED && p==XR_NULL_HANDLE);
    frame.layerCount=1;frame.layers=&layers[1];
    assert(xrEndFrame(s,&frame)==XR_SUCCESS && observed_count==1);
    puts("Passthrough behavioral tests passed");
}
