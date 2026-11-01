package com.hydro.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.hydro.app.core.auth.SessionManager
import com.hydro.app.core.prefs.PreferencesDataSource
import com.hydro.app.features.auth.data.AuthRepository
import com.hydro.app.ui.screens.AlertsScreen
import com.hydro.app.ui.screens.GreenhousesScreen
import com.hydro.app.ui.screens.LoginScreen
import com.hydro.app.ui.screens.NodeDetailsScreen
import com.hydro.app.ui.screens.ProvisioningScreen
import com.hydro.app.ui.screens.ServerSettingsScreen
import com.hydro.app.ui.screens.ZoneDetailsScreen
import com.hydro.app.ui.screens.ZonesScreen
import com.hydro.app.ui.theme.HydroTheme
import dagger.hilt.android.AndroidEntryPoint
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { HydroAppRoot() }
    }
}

@Composable
fun HydroAppRoot() {
    val session: SessionManagerViewModel = hiltViewModel()
    val navController = rememberNavController()
    val lifecycleOwner = LocalLifecycleOwner.current
    val scope = rememberCoroutineScope()
    val tokenState by session.preferences.tokenFlow.collectAsState(initial = null)
    val currentRoute = navController.currentBackStackEntryAsState().value?.destination?.route
    val publicRoute = currentRoute == Routes.LOGIN || currentRoute == Routes.SETTINGS

    LaunchedEffect(tokenState) {
        if (tokenState != null) {
            session.sessionManager.startSessionMonitoring(session.viewModelScope) {
                session.viewModelScope.launch { session.authRepository.logout() }
            }
        } else {
            session.sessionManager.stopSessionMonitoring()
        }
    }

    LaunchedEffect(currentRoute) {
        if (tokenState != null && currentRoute != null) {
            session.sessionManager.updateActivity()
        }
    }

    DisposableEffect(lifecycleOwner, tokenState) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME && tokenState != null) {
                session.viewModelScope.launch { session.sessionManager.updateActivity() }
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    LaunchedEffect(tokenState, currentRoute) {
        if (tokenState != null && currentRoute == Routes.LOGIN) {
            navController.navigate(Routes.GREENHOUSES) {
                popUpTo(Routes.LOGIN) { inclusive = true }
            }
        } else if (tokenState == null && currentRoute != null && !publicRoute) {
            navController.navigate(Routes.LOGIN) {
                popUpTo(0) { inclusive = true }
            }
        }
    }

    HydroTheme {
        Surface {
            HydroNavHost(
                navController = navController,
                onLogout = { scope.launch { session.authRepository.logout() } },
            )
        }
    }
}

@HiltViewModel
class SessionManagerViewModel @Inject constructor(
    val sessionManager: SessionManager,
    val authRepository: AuthRepository,
    val preferences: PreferencesDataSource,
) : ViewModel()

object Routes {
    const val LOGIN = "login"
    const val SETTINGS = "settings"
    const val GREENHOUSES = "greenhouses"
    const val ZONES = "zones/{greenhouseId}"
    const val ZONE_DETAILS = "zone_details/{zoneId}"
    const val NODE_DETAILS = "node/{nodeId}"
    const val ALERTS = "alerts"
    const val PROVISIONING = "provisioning"
}

@Composable
fun HydroNavHost(
    navController: NavHostController,
    onLogout: () -> Unit,
    modifier: Modifier = Modifier,
) {
    NavHost(navController = navController, startDestination = Routes.LOGIN, modifier = modifier) {
        composable(Routes.LOGIN) {
            LoginScreen(
                onLoggedIn = {
                    navController.navigate(Routes.GREENHOUSES) {
                        popUpTo(Routes.LOGIN) { inclusive = true }
                    }
                },
                onOpenSettings = { navController.navigate(Routes.SETTINGS) },
            )
        }
        composable(Routes.SETTINGS) {
            ServerSettingsScreen(onBack = { navController.popBackStack() })
        }
        composable(Routes.GREENHOUSES) {
            GreenhousesScreen(
                onOpenZones = { greenhouseId ->
                    navController.navigate("zones/$greenhouseId")
                },
                onOpenAlerts = { navController.navigate(Routes.ALERTS) },
                onOpenSettings = { navController.navigate(Routes.SETTINGS) },
                onProvisioning = { navController.navigate(Routes.PROVISIONING) },
                onLogout = onLogout,
            )
        }
        composable(
            route = Routes.ZONES,
            arguments = listOf(navArgument("greenhouseId") { type = NavType.IntType }),
        ) { entry ->
            val greenhouseId = entry.arguments?.getInt("greenhouseId") ?: return@composable
            ZonesScreen(
                greenhouseId = greenhouseId,
                onOpenZone = { zoneId -> navController.navigate("zone_details/$zoneId") },
                onBack = { navController.popBackStack() },
            )
        }
        composable(
            route = Routes.ZONE_DETAILS,
            arguments = listOf(navArgument("zoneId") { type = NavType.IntType }),
        ) { entry ->
            val zoneId = entry.arguments?.getInt("zoneId") ?: return@composable
            ZoneDetailsScreen(
                zoneId = zoneId,
                onOpenNode = { nodeId -> navController.navigate("node/$nodeId") },
                onBack = { navController.popBackStack() },
            )
        }
        composable(
            route = Routes.NODE_DETAILS,
            arguments = listOf(navArgument("nodeId") { type = NavType.IntType }),
        ) { entry ->
            val nodeId = entry.arguments?.getInt("nodeId") ?: return@composable
            NodeDetailsScreen(nodeId = nodeId, onBack = { navController.popBackStack() })
        }
        composable(Routes.ALERTS) {
            AlertsScreen(onBack = { navController.popBackStack() })
        }
        composable(Routes.PROVISIONING) {
            ProvisioningScreen(onBack = { navController.popBackStack() })
        }
    }
}
