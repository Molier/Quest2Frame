// SPDX-License-Identifier: GPL-3.0-only
// gcc -Wall -Wextra -Werror -I native/test_stubs -I native/include native/test_refresh.c -ldl -lpthread -o /tmp/q2f-refresh-test
#include "frame_bridge.c"
#include <assert.h>
static int offered=1, requested_count, extension_count;
static float requested;
static XrResult begin_result=XR_SUCCESS, request_result=XR_SUCCESS;
static XrResult mock_extensions(const char *layer,uint32_t cap,uint32_t *count,XrExtensionProperties *props) {
    (void)layer; *count=offered;
    if (cap && offered) strcpy(props[0].extensionName, XR_FB_DISPLAY_REFRESH_RATE_EXTENSION_NAME);
    return XR_SUCCESS;
}
static XrResult mock_create(const XrInstanceCreateInfo *info,XrInstance *instance) {
    extension_count=0;
    for(uint32_t i=0;i<info->enabledExtensionCount;++i)
        if(!strcmp(info->enabledExtensionNames[i],XR_FB_DISPLAY_REFRESH_RATE_EXTENSION_NAME)) ++extension_count;
    *instance=(XrInstance)(uintptr_t)1; return XR_SUCCESS;
}
static XrResult mock_rates(XrSession session,uint32_t cap,uint32_t *count,float *rates) {
    (void)session; *count=2; if(cap>=2) {rates[0]=72;rates[1]=90;} return XR_SUCCESS;
}
static XrResult mock_request(XrSession session,float rate) {
    (void)session; requested=rate; ++requested_count; return request_result;
}
static XrResult mock_begin(XrSession session,const XrSessionBeginInfo *info) {
    (void)session;(void)info; return begin_result;
}
static XrResult mock_proc(XrInstance instance,const char *name,PFN_xrVoidFunction *fn) {
    (void)instance; *fn=NULL;
#define MOCK(n,f) if(!strcmp(name,n)) *fn=(PFN_xrVoidFunction)f
    MOCK("xrEnumerateInstanceExtensionProperties",mock_extensions);
    MOCK("xrCreateInstance",mock_create);
    MOCK("xrEnumerateDisplayRefreshRatesFB",mock_rates);
    MOCK("xrRequestDisplayRefreshRateFB",mock_request);
    MOCK("xrBeginSession",mock_begin);
    return *fn?XR_SUCCESS:XR_ERROR_FUNCTION_UNSUPPORTED;
}
static void noop(void) {}
int main(void) {
    pthread_once(&once,noop); original=mock_proc;
    XrInstanceCreateInfo info={.type=XR_TYPE_INSTANCE_CREATE_INFO}; XrInstance instance;
    assert(xrCreateInstance(&info,&instance)==XR_SUCCESS && extension_count==1);
    XrSession session=(XrSession)(uintptr_t)2;
    refresh_rate=90;
    assert(xrBeginSession(session,NULL)==XR_SUCCESS && requested==90 && requested_count==1);
    assert(xrRequestDisplayRefreshRateFB(session,72)==XR_SUCCESS && requested==90);
    refresh_rate=120; requested_count=0;
    assert(xrBeginSession(session,NULL)==XR_SUCCESS && requested_count==0);
    assert(xrRequestDisplayRefreshRateFB(session,72)==XR_SUCCESS && requested==72);
    refresh_rate=0; requested_count=0;
    assert(xrBeginSession(session,NULL)==XR_SUCCESS && requested_count==0);
    assert(xrRequestDisplayRefreshRateFB(session,72)==XR_SUCCESS && requested==72);
    refresh_rate=90; request_result=XR_ERROR_RUNTIME_FAILURE;
    assert(xrBeginSession(session,NULL)==XR_SUCCESS); // preference cannot fail startup
    begin_result=XR_ERROR_SESSION_RUNNING; requested_count=0;
    assert(xrBeginSession(session,NULL)==XR_ERROR_SESSION_RUNNING && requested_count==0);
    begin_result=XR_SUCCESS;
    const char *names[]={XR_FB_DISPLAY_REFRESH_RATE_EXTENSION_NAME};
    info.enabledExtensionCount=1;info.enabledExtensionNames=names;
    assert(xrCreateInstance(&info,&instance)==XR_SUCCESS && extension_count==1);
    offered=0;info.enabledExtensionCount=0;info.enabledExtensionNames=NULL;
    assert(xrCreateInstance(&info,&instance)==XR_SUCCESS && extension_count==0);
    assert(xrBeginSession(session,NULL)==XR_SUCCESS && requested_count==0);
    puts("Refresh-rate behavior tests passed"); return 0;
}
