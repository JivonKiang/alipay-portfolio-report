package com.jivon.portfolio;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        // Capacitor SystemBars plugin automatically handles safe area insets
        // via capacitor.config.json: plugins.SystemBars.insetsHandling = "css"
    }
}
