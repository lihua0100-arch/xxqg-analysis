#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <objc/runtime.h>
#import <objc/message.h>

static void enableHUD(UIViewController *vc) {
    SEL sel = NSSelectorFromString(@"setHUDEnabled:");
    if ([vc respondsToSelector:sel]) {
        ((void(*)(id, SEL, BOOL))objc_msgSend)(vc, sel, YES);
    }
}

__attribute__((constructor))
static void init(void) {
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 3 * NSEC_PER_SEC),
                   dispatch_get_main_queue(), ^{
        // Try RootViewController from key window
        UIWindow *win = [UIApplication sharedApplication].keyWindow;
        UIViewController *vc = win.rootViewController;
        while (vc) {
            if ([vc isKindOfClass:NSClassFromString(@"RootViewController")]) {
                enableHUD(vc);
                break;
            }
            if ([vc isKindOfClass:NSClassFromString(@"HUDRootViewController")]) {
                enableHUD(vc);
                break;
            }
            vc = vc.presentedViewController;
        }
    });
}
