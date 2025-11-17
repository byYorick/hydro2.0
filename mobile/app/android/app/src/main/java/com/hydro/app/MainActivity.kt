package com.hydro.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.hydro.app.ui.screens.AlertsScreen
import com.hydro.app.ui.screens.GreenhousesScreen
import com.hydro.app.ui.screens.LoginScreen
import com.hydro.app.ui.screens.ProvisioningScreen
import com.hydro.app.ui.screens.ZoneDetailsScreen
import com.hydro.app.ui.screens.ZonesScreen
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
	override fun onCreate(savedInstanceState: Bundle?) {
		super.onCreate(savedInstanceState)
		setContent {
			HydroAppRoot()
		}
	}
}

@Composable
fun HydroAppRoot() {
	val navController = rememberNavController()
	val snackbarHostState = remember { SnackbarHostState() }
	MaterialTheme {
		Surface {
			SnackbarHost(hostState = snackbarHostState)
			HydroNavHost(navController = navController)
		}
	}
}

object Routes {
	const val LOGIN = "login"
	const val GREENHOUSES = "greenhouses"
	const val ZONES = "zones"
	const val ZONE_DETAILS = "zone_details/{zoneId}"
	const val ALERTS = "alerts"
	const val PROVISIONING = "provisioning"
}

@Composable
fun HydroNavHost(navController: NavHostController, modifier: Modifier = Modifier) {
	NavHost(
		navController = navController,
		startDestination = Routes.LOGIN
	) {
		composable(Routes.LOGIN) {
			LoginScreen(onLoggedIn = {
				navController.navigate(Routes.GREENHOUSES) {
					popUpTo(Routes.LOGIN) { inclusive = true }
				}
			})
		}
		composable(Routes.GREENHOUSES) {
			GreenhousesScreen(
				onOpenZones = { navController.navigate(Routes.ZONES) },
				onOpenAlerts = { navController.navigate(Routes.ALERTS) },
				onProvisioning = { navController.navigate(Routes.PROVISIONING) }
			)
		}
		composable(Routes.ZONES) {
			ZonesScreen(onOpenZone = { zoneId ->
				navController.navigate("zone_details/$zoneId")
			})
		}
		composable("zone_details/{zoneId}") {
			ZoneDetailsScreen(onBack = { navController.popBackStack() })
		}
		composable(Routes.ALERTS) {
			AlertsScreen(onBack = { navController.popBackStack() })
		}
		composable(Routes.PROVISIONING) {
			ProvisioningScreen(onBack = { navController.popBackStack() })
		}
	}
}


