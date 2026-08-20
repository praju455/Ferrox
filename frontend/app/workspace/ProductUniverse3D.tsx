"use client";

import React, { useEffect, useRef } from "react";

export default function ProductUniverse3D() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let width = window.innerWidth;
    let height = window.innerHeight;
    canvas.width = width;
    canvas.height = height;

    const handleResize = () => {
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = width;
      canvas.height = height;
    };
    window.addEventListener("resize", handleResize);

    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // Meteor structure
    interface Meteor {
      x: number;
      y: number;
      speed: number;
      length: number;
      thickness: number;
      opacity: number;
    }

    const meteors: Meteor[] = [];
    const maxMeteors = 12; // Keep it between 8-15 as requested

    const spawnMeteor = (initial = false) => {
      // Spawn along the top edge or right edge to ensure diagonal path crosses the screen
      const spawnTop = Math.random() > 0.5;
      let x, y;
      
      if (initial) {
        x = Math.random() * width;
        y = Math.random() * height;
      } else if (spawnTop) {
        x = Math.random() * (width + height); // Can spawn far right to cross the bottom
        y = -200;
      } else {
        x = width + 200;
        y = Math.random() * height - 200;
      }

      meteors.push({
        x,
        y,
        speed: 2 + Math.random() * 4, // different falling speeds
        length: 100 + Math.random() * 200, // length of the tail
        thickness: 0.5 + Math.random() * 1.5, // slight variation in size
        opacity: 0.1 + Math.random() * 0.3, // low opacity, occasional brighter one
      });
    };

    // Initial spawn
    for (let i = 0; i < maxMeteors; i++) {
      spawnMeteor(true);
    }

    let animationFrameId: number;

    const render = () => {
      ctx.clearRect(0, 0, width, height);
      
      // Stop animation if reduced motion is enabled
      if (prefersReducedMotion) {
        return;
      }

      for (let i = meteors.length - 1; i >= 0; i--) {
        const m = meteors[i];
        
        // Move diagonally (top-right to bottom-left)
        // dx is negative (left), dy is positive (down)
        m.x -= m.speed;
        m.y += m.speed;

        // Calculate tail end (opposite direction of movement)
        const tailX = m.x + m.length;
        const tailY = m.y - m.length;

        // Draw meteor
        ctx.beginPath();
        ctx.moveTo(tailX, tailY);
        ctx.lineTo(m.x, m.y);
        
        // Gradient for fading tail
        const grad = ctx.createLinearGradient(tailX, tailY, m.x, m.y);
        grad.addColorStop(0, `rgba(255, 107, 0, 0)`); // Ferrox orange, fully transparent at tail
        grad.addColorStop(0.8, `rgba(255, 107, 0, ${m.opacity * 0.5})`);
        grad.addColorStop(1, `rgba(255, 107, 0, ${m.opacity})`); // Brightest at core
        
        ctx.strokeStyle = grad;
        ctx.lineWidth = m.thickness;
        ctx.lineCap = "round";
        
        // Excessive glow effect for all meteoroids
        ctx.shadowBlur = 25;
        ctx.shadowColor = "#FF6B00";

        ctx.stroke();
        ctx.shadowBlur = 0; // reset

        // Remove if off-screen (bottom-left)
        if (m.x < -m.length || m.y > height + m.length) {
          meteors.splice(i, 1);
          // Spawn a new one to replace it
          if (meteors.length < maxMeteors) {
            spawnMeteor();
          }
        }
      }

      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      window.removeEventListener("resize", handleResize);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        width: "100%",
        height: "100%",
        pointerEvents: "none",
        zIndex: 0,
        opacity: 0.8, // Increased opacity to make glow pop
        background: "transparent",
      }}
    />
  );
}
