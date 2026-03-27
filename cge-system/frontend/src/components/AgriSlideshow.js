import React, { useState, useEffect } from 'react';

const IMAGES = [
    'https://images.unsplash.com/photo-1500937386664-56d1dfef3854?w=1600&q=80',
    'https://images.unsplash.com/photo-1464226184884-fa280b87c399?w=1600&q=80',
    'https://images.unsplash.com/photo-1416879595882-3373a0480b5b?w=1600&q=80',
    'https://images.unsplash.com/photo-1574323347407-f5e1ad6d020b?w=1600&q=80',
    'https://images.unsplash.com/photo-1625246333195-78d9c38ad449?w=1600&q=80',
];

export default function AgriSlideshow() {
    const [currentIndex, setCurrentIndex] = useState(0);
    const [isTransitioning, setIsTransitioning] = useState(false);

    useEffect(() => {
        const interval = setInterval(() => {
            setIsTransitioning(true);
            setTimeout(() => {
                setCurrentIndex((prev) => (prev + 1) % IMAGES.length);
                setIsTransitioning(false);
            }, 1200);
        }, 5000);
        return () => clearInterval(interval);
    }, []);

    const nextIndex = (currentIndex + 1) % IMAGES.length;

    return (
        <div className="slideshow-container">
            <img
                src={IMAGES[currentIndex]}
                alt=""
                className="slideshow-image"
                style={{
                    opacity: isTransitioning ? 0 : 1,
                    transform: `scale(${isTransitioning ? 1.06 : 1})`,
                    transition: 'opacity 1.2s ease-in-out, transform 5s ease-in-out',
                }}
            />
            <img
                src={IMAGES[nextIndex]}
                alt=""
                className="slideshow-image"
                style={{
                    opacity: isTransitioning ? 1 : 0,
                    transform: 'scale(1)',
                    transition: 'opacity 1.2s ease-in-out, transform 5s ease-in-out',
                }}
            />
            <div className="slideshow-overlay" />
        </div>
    );
}
