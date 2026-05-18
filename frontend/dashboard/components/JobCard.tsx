'use client';

import Link from 'next/link';
import { MapPin, ExternalLink, Mail } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import StatusBadge from './StatusBadge';
import type { Job } from '../lib/api';

interface JobCardProps {
  job: Job;
}

export default function JobCard({ job }: JobCardProps) {
  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-4 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <Link
            href={`/jobs/${job.id}`}
            className="font-semibold text-gray-900 dark:text-gray-100 hover:text-blue-600 dark:hover:text-blue-400 block truncate"
          >
            {job.job_title}
          </Link>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-0.5">{job.company}</p>
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          <StatusBadge status={job.status} />
          <StatusBadge status={job.source_portal} />
        </div>
      </div>

      <div className="mt-3 flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
        {job.location && (
          <span className="flex items-center gap-1">
            <MapPin size={12} />
            {job.location}
          </span>
        )}
        {job.hr_email && (
          <span className="flex items-center gap-1 text-green-600 dark:text-green-400">
            <Mail size={12} />
            HR email found
          </span>
        )}
        {job.relevance_score != null && (
          <span className="text-blue-600 dark:text-blue-400 font-medium">
            {(job.relevance_score * 100).toFixed(0)}% match
          </span>
        )}
      </div>

      <div className="mt-2 flex items-center justify-between">
        <span className="text-xs text-gray-400 dark:text-gray-500">
          {job.scraped_at
            ? `Scraped ${formatDistanceToNow(new Date(job.scraped_at), { addSuffix: true })}`
            : 'Recently scraped'}
        </span>
        <a
          href={job.job_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-blue-500 hover:text-blue-600 flex items-center gap-1"
        >
          View <ExternalLink size={10} />
        </a>
      </div>
    </div>
  );
}
