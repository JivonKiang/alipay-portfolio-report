package com.jivon.portfolio;

import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.webkit.WebView;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.graphics.Insets;
import android.view.View;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    private int lastTop = -1;
    private int lastBottom = -1;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
    }

    @Override
    public void onStart() {
        super.onStart();
        scheduleInsetInjection();
    }

    private void scheduleInsetInjection() {
        Handler handler = new Handler(Looper.getMainLooper());
        // Retry injection multiple times with delays to ensure WebView is ready
        for (int delay : new int[]{100, 300, 600, 1000, 2000}) {
            handler.postDelayed(this::injectInsets, delay);
        }
    }

    private void injectInsets() {
        try {
            WebView webView = getBridge().getWebView();
            if (webView == null) return;

            View rootView = getWindow().getDecorView();
            WindowInsetsCompat insets = ViewCompat.getRootWindowInsets(rootView);
            if (insets == null) return;

            Insets systemBars = insets.getInsets(WindowInsetsCompat.Type.systemBars());
            Insets cutout = insets.getInsets(WindowInsetsCompat.Type.displayCutout());
            Insets gestureNav = insets.getInsets(WindowInsetsCompat.Type.systemGestures());

            int topInset = Math.max(systemBars.top, cutout.top);
            int bottomInset = Math.max(Math.max(systemBars.bottom, gestureNav.bottom), 0);
            int leftInset = Math.max(systemBars.left, cutout.left);
            int rightInset = Math.max(systemBars.right, cutout.right);

            // Skip if values haven't changed
            if (topInset == lastTop && bottomInset == lastBottom) return;
            lastTop = topInset;
            lastBottom = bottomInset;

            String js = "javascript:(function(){" +
                "try{" +
                "var s=document.documentElement.style;" +
                "s.setProperty('--safe-area-inset-top','" + topInset + "px');" +
                "s.setProperty('--safe-area-inset-bottom','" + bottomInset + "px');" +
                "s.setProperty('--safe-area-inset-left','" + leftInset + "px');" +
                "s.setProperty('--safe-area-inset-right','" + rightInset + "px');" +
                "s.setProperty('--status-bar-height','" + topInset + "px');" +
                "s.setProperty('--navigation-bar-height','" + bottomInset + "px');" +
                // Also force body padding
                "document.body.style.paddingTop='" + topInset + "px';" +
                "document.body.style.paddingBottom='" + bottomInset + "px';" +
                // Force header padding
                "var h=document.querySelector('.app-header');" +
                "if(h)h.style.paddingTop='" + (topInset + 12) + "px';" +
                // Force bottom nav padding
                "var n=document.querySelector('.bottom-nav');" +
                "if(n)n.style.paddingBottom='" + (bottomInset + 6) + "px';" +
                "console.log('[Insets] top=" + topInset + " bottom=" + bottomInset + "');" +
                "}catch(e){}" +
                "})();";

            webView.post(() -> webView.evaluateJavascript(js, null));
        } catch (Exception e) {
            // Bridge not ready yet, will retry
        }
    }
}
