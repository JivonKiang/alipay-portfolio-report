#!/usr/bin/env python3
"""
Generate PWA icons for portfolio report app
Style: Dark finance aesthetic with gradient accent
"""

from PIL import Image, ImageDraw, ImageFilter
import math

def create_icon(size, filename):
    """Create a single icon size"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Background - dark slate
    bg_color = (15, 23, 42)  # #0f172a
    draw.rounded_rectangle([0, 0, size-1, size-1], radius=size//8, fill=bg_color)
    
    # Inner glow effect
    glow = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    
    # Gradient accent bar at top
    bar_height = max(3, size // 32)
    for i in range(bar_height):
        alpha = int(255 * (1 - i / bar_height) * 0.8)
        glow_draw.line(
            [(size//8, size//8 + i), (size - size//8, size//8 + i)],
            fill=(59, 130, 246, alpha)  # blue
        )
    
    # Chart line - stylized upward trend
    margin = size // 4
    chart_area = size - 2 * margin
    
    # Draw chart area background
    chart_bg = (30, 41, 59, 255)  # slightly lighter
    draw.rounded_rectangle(
        [margin, margin + bar_height, size - margin, size - margin//2],
        radius=size//20,
        fill=chart_bg
    )
    
    # Upward trend line points
    points = [
        (margin + chart_area * 0.15, margin + bar_height + chart_area * 0.65),
        (margin + chart_area * 0.35, margin + bar_height + chart_area * 0.55),
        (margin + chart_area * 0.55, margin + bar_height + chart_area * 0.45),
        (margin + chart_area * 0.75, margin + bar_height + chart_area * 0.30),
        (margin + chart_area * 0.90, margin + bar_height + chart_area * 0.15),
    ]
    
    # Draw line with glow
    line_width = max(2, size // 40)
    
    # Glow layer
    glow_layer = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    glow_draw2 = ImageDraw.Draw(glow_layer)
    glow_draw2.line(points, fill=(168, 85, 247, 120), width=line_width * 3)
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=line_width))
    
    # Main line
    draw.line(points, fill=(168, 85, 247, 255), width=line_width)
    
    # End dot
    end_x, end_y = points[-1]
    dot_radius = max(4, size // 28)
    draw.ellipse(
        [end_x - dot_radius, end_y - dot_radius, end_x + dot_radius, end_y + dot_radius],
        fill=(168, 85, 247, 255)
    )
    
    # Inner dot
    inner_radius = dot_radius // 2
    draw.ellipse(
        [end_x - inner_radius, end_y - inner_radius, end_x + inner_radius, end_y + inner_radius],
        fill=(255, 255, 255, 255)
    )
    
    # Area fill under line
    fill_points = points + [
        (margin + chart_area * 0.90, size - margin//2),
        (margin, size - margin//2)
    ]
    
    # Create gradient fill
    fill_img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    fill_draw = ImageDraw.Draw(fill_img)
    fill_draw.polygon(fill_points, fill=(168, 85, 247, 30))
    
    # Compose layers
    img = Image.alpha_composite(img, fill_img)
    img = Image.alpha_composite(img, glow_layer)
    
    # Redraw line and dot on top
    final_draw = ImageDraw.Draw(img)
    final_draw.line(points, fill=(168, 85, 247, 255), width=line_width)
    final_draw.ellipse(
        [end_x - dot_radius, end_y - dot_radius, end_x + dot_radius, end_y + dot_radius],
        fill=(168, 85, 247, 255)
    )
    final_draw.ellipse(
        [end_x - inner_radius, end_y - inner_radius, end_x + inner_radius, end_y + inner_radius],
        fill=(255, 255, 255, 255)
    )
    
    # Add subtle border
    border_width = max(1, size // 128)
    final_draw.rounded_rectangle(
        [border_width//2, border_width//2, size - 1 - border_width//2, size - 1 - border_width//2],
        radius=size//8,
        outline=(59, 130, 246, 60),
        width=border_width
    )
    
    img.save(filename, 'PNG')
    print(f"Created {filename} ({size}x{size})")

if __name__ == '__main__':
    create_icon(192, '/data/user/work/repo/icon-192.png')
    create_icon(512, '/data/user/work/repo/icon-512.png')
    print("Done!")
