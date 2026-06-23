package com.jivon.portfolio;

import android.os.Bundle;
import android.webkit.WebView;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.graphics.Insets;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // Enable edge-to-edge mode (required for Android 15+)
        WindowCompat.setDecorFitsSystemWindows(getWindow(), false);

        // Inject safe area insets into WebView as CSS variables
        // This fixes the issue where env(safe-area-inset-*) doesn't work
        // correctly in Android WebView on notch/punch-hole devices
        ViewCompat.setOnApplyWindowInsetsListener(
            getWindow().getDecorView().getRootView(),
            (view, windowInsets) -> {
                Insets systemBars = windowInsets.getInsets(WindowInsetsCompat.Type.systemBars());
                Insets cutout = windowInsets.getInsets(WindowInsetsCompat.Type.displayCutout());

                int topInset = Math.max(systemBars.top, cutout.top);
                int bottomInset = Math.max(systemBars.bottom, cutout.bottom);
                int leftInset = Math.max(systemBars.left, cutout.left);
                int rightInset = Math.max(systemBars.right, cutout.right);

                // Inject CSS variables into the WebView
                injectSafeAreaInsets(topInset, bottomInset, leftInset, rightInset);

                return WindowInsetsCompat.CONSUMED;
            }
        );
    }

    private void injectSafeAreaInsets(int top, int bottom, int left, int right) {
        // Wait for bridge to be ready then inject CSS
        getBridge().getWebView().post(() -> {
            String js = "javascript:(function() {" +
                "var style = document.documentElement.style;" +
                "style.setProperty('--safe-area-inset-top', '" + top + "px');" +
                "style.setProperty('--safe-area-inset-bottom', '" + bottom + "px');" +
                "style.setProperty('--safe-area-inset-left', '" + left + "px');" +
                "style.setProperty('--safe-area-inset-right', '" + right + "px');" +
                "style.setProperty('--status-bar-height', '" + top + "px');" +
                "style.setProperty('--navigation-bar-height', '" + bottom + "px');" +
                "console.log('[MainActivity] Insets injected: top=" + top + ", bottom=" + bottom + "');" +
                "})();";
            getBridge().getWebView().evaluateJavascript(js, null);
        });
    }
}
