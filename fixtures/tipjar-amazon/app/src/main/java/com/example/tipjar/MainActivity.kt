package com.example.tipjar

import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import com.amazon.device.iap.PurchasingListener
import com.amazon.device.iap.PurchasingService
import com.amazon.device.iap.model.ProductDataResponse
import com.amazon.device.iap.model.PurchaseResponse
import com.amazon.device.iap.model.PurchaseUpdatesResponse
import com.amazon.device.iap.model.UserDataResponse

class MainActivity : AppCompatActivity(), PurchasingListener {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        PurchasingService.registerListener(applicationContext, this)
        PurchasingService.getUserData()
    }

    override fun onUserDataResponse(response: UserDataResponse) {
        // no-op for demo
    }

    override fun onProductDataResponse(response: ProductDataResponse) {
        // no-op for demo
    }

    override fun onPurchaseResponse(response: PurchaseResponse) {
        // no-op for demo
    }

    override fun onPurchaseUpdatesResponse(response: PurchaseUpdatesResponse) {
        // no-op for demo
    }
}
