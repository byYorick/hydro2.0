package com.hydro.app.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val HydroDark = darkColorScheme(
    primary = Color(0xFF7DFFB3),
    onPrimary = Color(0xFF00331A),
    primaryContainer = Color(0xFF0F3D28),
    onPrimaryContainer = Color(0xFFB8FFD4),
    secondary = Color(0xFF9FD4FF),
    onSecondary = Color(0xFF042033),
    background = Color(0xFF0C1210),
    onBackground = Color(0xFFE7F3EC),
    surface = Color(0xFF141C19),
    onSurface = Color(0xFFE7F3EC),
    surfaceVariant = Color(0xFF24302B),
    onSurfaceVariant = Color(0xFFC5D5CC),
    error = Color(0xFFFF8A96),
    onError = Color(0xFF3B0610),
    errorContainer = Color(0xFF5C1822),
    outline = Color(0xFF3E5248),
)

@Composable
fun HydroTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = HydroDark,
        content = content,
    )
}
