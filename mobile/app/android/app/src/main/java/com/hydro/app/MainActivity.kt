package com.hydro.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.hydro.app.core.prefs.PreferencesDataSource
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
	val context = LocalContext.current
	val prefs = remember { PreferencesDataSource(context) }
	val tokenState by prefs.tokenFlow.collectAsState(initial = null)
	val currentBackStackEntry by navController.currentBackStackEntryAsState()
	val currentRoute = currentBackStackEntry?.destination?.route
	
	LaunchedEffect(tokenState, currentRoute) {
		if (tokenState != null && currentRoute == Routes.LOGIN) {
			navController.navigate(Routes.GREENHOUSES) {
				popUpTo(Routes.LOGIN) { inclusive = true }
			}
		} else if (tokenState == null && currentRoute != null && currentRoute != Routes.LOGIN) {
			navController.navigate(Routes.LOGIN) {
				popUpTo(0) { inclusive = true }
			}
		}
	}
	
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
	const val ZONES = "zones/{greenhouseId}"
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
				onOpenZones = { greenhouseId ->
					navController.navigate(Routes.ZONES.replace("{greenhouseId}", greenhouseId.toString()))
				},
				onOpenAlerts = { navController.navigate(Routes.ALERTS) },
				onProvisioning = { navController.navigate(Routes.PROVISIONING) }
			)
		}
		composable(Routes.ZONES) { backStackEntry ->
			val greenhouseId = backStackEntry.arguments?.getString("greenhouseId")?.toIntOrNull()
			if (greenhouseId != null) {
			ZonesScreen(
				greenhouseId = greenhouseId,
				onOpenZone = { zoneId ->
					navController.navigate(Routes.ZONE_DETAILS.replace("{zoneId}", zoneId.toString()))
				},
				onBack = { navController.popBackStack() }
			)
			} else {
				// Invalid navigation - redirect to greenhouses
				LaunchedEffect(Unit) {
					navController.navigate(Routes.GREENHOUSES) {
						popUpTo(Routes.GREENHOUSES) { inclusive = true }
					}
				}
			}
		}
		composable(Routes.ZONE_DETAILS) { backStackEntry ->
			val zoneId = backStackEntry.arguments?.getString("zoneId")?.toIntOrNull()
			if (zoneId != null && zoneId > 0) {
			ZoneDetailsScreen(
				zoneId = zoneId,
				onBack = { navController.popBackStack() }
			)
			} else {
				// Invalid navigation - redirect to greenhouses
				LaunchedEffect(Unit) {
					navController.navigate(Routes.GREENHOUSES) {
						popUpTo(Routes.GREENHOUSES) { inclusive = true }
					}
				}
			}
		}
		composable(Routes.ALERTS) {
			AlertsScreen(onBack = { navController.popBackStack() })
		}
		composable(Routes.PROVISIONING) {
			ProvisioningScreen(onBack = { navController.popBackStack() })
		}
	}
}


