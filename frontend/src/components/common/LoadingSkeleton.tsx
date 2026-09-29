"use client";

import React from "react";

export function TableSkeleton({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="w-full rounded-2xl border border-gray-800 bg-gray-900/40 p-4 animate-pulse">
      <div className="h-8 bg-gray-800 rounded-lg mb-4 w-1/3" />
      <div className="space-y-3">
        {Array.from({ length: rows }).map((_, rIdx) => (
          <div key={rIdx} className="flex gap-4">
            {Array.from({ length: cols }).map((_, cIdx) => (
              <div key={cIdx} className="h-6 bg-gray-800/60 rounded flex-1" />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

export function CardSkeleton() {
  return (
    <div className="rounded-2xl border border-gray-800 bg-gray-900/40 p-6 animate-pulse">
      <div className="h-4 bg-gray-800 rounded w-1/2 mb-3" />
      <div className="h-8 bg-gray-700/80 rounded w-3/4 mb-4" />
      <div className="h-3 bg-gray-800 rounded w-1/3" />
    </div>
  );
}
