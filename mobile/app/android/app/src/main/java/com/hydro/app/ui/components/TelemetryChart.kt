package com.hydro.app.ui.components

import android.graphics.Paint
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.unit.dp
import com.hydro.app.core.domain.TelemetryHistoryPoint
import kotlin.math.max

@Composable
fun TelemetryChart(
    data: List<TelemetryHistoryPoint>,
    modifier: Modifier = Modifier,
    lineColor: Color = MaterialTheme.colorScheme.primary,
    backgroundColor: Color = MaterialTheme.colorScheme.surfaceVariant
) {
    if (data.isEmpty()) {
        Box(
            modifier = modifier
                .clip(RoundedCornerShape(8.dp))
                .background(backgroundColor)
                .fillMaxWidth()
                .height(200.dp),
            contentAlignment = Alignment.Center
        ) {
            Text(
                text = "Нет данных",
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
        return
    }

    Box(
        modifier = modifier
            .clip(RoundedCornerShape(8.dp))
            .background(backgroundColor)
            .fillMaxWidth()
            .height(200.dp)
    ) {
        Canvas(
            modifier = Modifier.fillMaxSize()
        ) {
            val padding = 16.dp.toPx()
            val chartWidth = size.width - padding * 2
            val chartHeight = size.height - padding * 2

            // Find min and max values
            val values = data.mapNotNull { it.value }
            if (values.isEmpty()) return@Canvas

            val minValue = values.minOrNull() ?: 0.0
            val maxValue = values.maxOrNull() ?: 1.0
            val valueRange = max(maxValue - minValue, 0.1) // Avoid division by zero

            // Draw grid lines
            val gridColor = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.1f)
            for (i in 0..4) {
                val y = padding + (chartHeight / 4) * i
                drawLine(
                    color = gridColor,
                    start = Offset(padding, y),
                    end = Offset(size.width - padding, y),
                    strokeWidth = 1.dp.toPx()
                )
            }

            // Draw data line
            val path = Path()
            val pointSize = 3.dp.toPx()
            val stepX = chartWidth / max(data.size - 1, 1)

            data.forEachIndexed { index, point ->
                val x = padding + stepX * index
                val normalizedValue = (point.value - minValue) / valueRange
                val y = padding + chartHeight - (normalizedValue * chartHeight)

                if (index == 0) {
                    path.moveTo(x, y)
                } else {
                    path.lineTo(x, y)
                }

                // Draw point
                drawCircle(
                    color = lineColor,
                    radius = pointSize,
                    center = Offset(x, y)
                )
            }

            // Draw line
            drawPath(
                path = path,
                color = lineColor,
                style = Stroke(width = 2.dp.toPx())
            )

            // Draw min/max labels (simplified - using native canvas)
            val textColor = MaterialTheme.colorScheme.onSurfaceVariant
            val textPaint = Paint().apply {
                color = textColor.toArgb()
                textSize = 10.dp.toPx()
                isAntiAlias = true
            }
            drawContext.canvas.nativeCanvas.apply {
                drawText(
                    String.format("%.1f", maxValue),
                    padding,
                    padding + 10.dp.toPx(),
                    textPaint
                )
                drawText(
                    String.format("%.1f", minValue),
                    padding,
                    size.height - padding,
                    textPaint
                )
            }
        }
    }
}

